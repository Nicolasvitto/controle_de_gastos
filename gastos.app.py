import json
import os
import csv
import uuid
import tempfile
from datetime import datetime, timedelta
from collections import defaultdict, deque
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog
import tkinter.font as tkfont

ARQUIVO_GASTOS = "gastos_pessoais.json"
BACKUP_DIR = "backups"

# Undo stack (last deletions)
_last_deleted = deque(maxlen=10)

# ---------- Helpers ----------
def parse_date_to_iso(s):
    """Tenta normalizar várias entradas de data para YYYY-MM-DD ou retorna None."""
    if not s or not str(s).strip():
        return None
    s = s.strip()
    formatos = ["%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%m/%d/%Y", "%Y/%m/%d"]
    for fmt in formatos:
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except:
            continue
    # tentar interpretar números sem separador (YYYYMMDD)
    if s.isdigit() and len(s) == 8:
        try:
            return datetime.strptime(s, "%Y%m%d").strftime("%Y-%m-%d")
        except:
            pass
    return None

def safe_float(v):
    try:
        return float(str(v).replace(",", "."))
    except:
        return None

# ---------- Arquivo: carregar / salvar (atômico e resiliência) ----------
def carregar_gastos():
    if os.path.exists(ARQUIVO_GASTOS):
        try:
            with open(ARQUIVO_GASTOS, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            os.makedirs(BACKUP_DIR, exist_ok=True)
            bak = os.path.join(BACKUP_DIR, f"corrupt_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
            try:
                os.replace(ARQUIVO_GASTOS, bak)
            except:
                pass
            messagebox.showwarning("Aviso", f"Arquivo de dados corrompido. Foi movido para:\n{bak}")
    return {"gastos": [], "orcamento_inicial": 0.0, "orcamentos_categoria": {}, "recorrentes": []}

def salvar_gastos(dados):
    dirpath = os.path.dirname(os.path.abspath(ARQUIVO_GASTOS)) or "."
    with tempfile.NamedTemporaryFile("w", dir=dirpath, delete=False, encoding="utf-8") as tmp:
        json.dump(dados, tmp, indent=4, ensure_ascii=False)
        tmp_path = tmp.name
    os.replace(tmp_path, ARQUIVO_GASTOS)

def fazer_backup():
    os.makedirs(BACKUP_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    destino = os.path.join(BACKUP_DIR, f"backup_{timestamp}.json")
    dados = carregar_gastos()
    with open(destino, "w", encoding="utf-8") as f:
        json.dump(dados, f, indent=4, ensure_ascii=False)
    messagebox.showinfo("Backup", f"Backup salvo em:\n{destino}")

def importar_arquivo(caminho):
    if not os.path.exists(caminho):
        messagebox.showerror("Importar", "Arquivo não encontrado.")
        return
    with open(caminho, "r", encoding="utf-8") as f:
        dados = json.load(f)
    salvar_gastos(dados)
    messagebox.showinfo("Importar", "Dados importados com sucesso.")
    app_refresh()

def exportar_csv(path="gastos_export.csv"):
    dados = carregar_gastos()
    with open(path, "w", newline="", encoding="utf-8") as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(["data","categoria","descricao","valor"])
        for g in dados["gastos"]:
            writer.writerow([g["data"], g.get("categoria","Geral"), g["descricao"], f"{g['valor']:.2f}"])
    messagebox.showinfo("Exportar CSV", f"Exportado para {path}")

# ---------- CSV import (mapeamento automático) ----------
def importar_csv(path=None):
    path = path or filedialog.askopenfilename(title="Importar CSV", filetypes=[("CSV","*.csv"),("All","*.*")])
    if not path:
        return
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        headers = next(reader, None)
        if not headers:
            messagebox.showerror("Importar CSV", "Arquivo CSV vazio.")
            return
        # mapear cabeçalhos
        hdr_map = {}
        for i,h in enumerate(headers):
            key = h.strip().lower()
            if key in ("data","date","dia"):
                hdr_map["data"] = i
            elif key in ("categoria","category"):
                hdr_map["categoria"] = i
            elif key in ("descricao","descrição","description","desc"):
                hdr_map["descricao"] = i
            elif key in ("valor","value","amount","amount_br"):
                hdr_map["valor"] = i
        # heurística: se não houver cabeçalho óbvio, tentar padrões por posição
        dados = carregar_gastos()
        adicionados = 0
        for row in reader:
            if not row:
                continue
            # obter valores com fallback
            raw_data = row[hdr_map["data"]] if "data" in hdr_map and hdr_map["data"] < len(row) else row[0] if len(row)>0 else ""
            raw_cat = row[hdr_map["categoria"]] if "categoria" in hdr_map and hdr_map["categoria"] < len(row) else (row[1] if len(row)>1 else "Geral")
            raw_desc = row[hdr_map["descricao"]] if "descricao" in hdr_map and hdr_map["descricao"] < len(row) else (row[2] if len(row)>2 else "Importado")
            raw_val = row[hdr_map["valor"]] if "valor" in hdr_map and hdr_map["valor"] < len(row) else (row[-1] if len(row)>0 else "0")
            data_iso = parse_date_to_iso(raw_data) or datetime.now().strftime("%Y-%m-%d")
            val = safe_float(raw_val) or 0.0
            gasto = {"id": str(uuid.uuid4()), "descricao": str(raw_desc).strip(), "valor": round(val,2), "data": data_iso, "categoria": str(raw_cat).strip() or "Geral"}
            dados["gastos"].append(gasto)
            adicionados += 1
        salvar_gastos(dados)
        messagebox.showinfo("Importar CSV", f"{adicionados} itens importados.")
        app_refresh()

# ---------- Recorrentes (aplicar) ----------
def aplicar_recorrentes(show_msg=True):
    dados = carregar_gastos()
    recs = dados.get("recorrentes", [])
    if not recs:
        if show_msg:
            messagebox.showinfo("Recorrentes", "Nenhuma despesa recorrente cadastrada.")
        return
    aplicados = 0
    hoje = datetime.now()
    for rec in recs:
        try:
            ultima = datetime.strptime(rec.get("ultima_geracao"), "%Y-%m-%d")
        except:
            ultima = hoje
        # gerar ocorrências mensais desde ultima até mês atual (simples)
        while True:
            proxima = (ultima.replace(day=1) + timedelta(days=32))
            # ajustar dia
            dia = min(rec.get("dia", ultima.day), 28)
            proxima = proxima.replace(day=dia)
            if proxima.date() > hoje.date():
                break
            # adicionar gasto somente se ainda não existir ocorrência com mesma marca
            existe = any(g.get("descricao")==rec["descricao"] and g.get("data")==proxima.strftime("%Y-%m-%d") and abs(g.get("valor",0)-rec["valor"])<0.01 for g in dados["gastos"])
            if not existe:
                dados["gastos"].append({
                    "id": str(uuid.uuid4()),
                    "descricao": rec["descricao"],
                    "valor": rec["valor"],
                    "data": proxima.strftime("%Y-%m-%d"),
                    "categoria": rec.get("categoria","Geral")
                })
                aplicados += 1
            ultima = proxima
        rec["ultima_geracao"] = ultima.strftime("%Y-%m-%d")
    if aplicados:
        salvar_gastos(dados)
        app_refresh()
    if show_msg:
        messagebox.showinfo("Recorrentes", f"Recorrentes aplicados: {aplicados}")

# ---------- GUI ----------
root = tk.Tk()
root.title("Gastos — Gerenciador")
root.geometry("1000x640")
root.minsize(900, 600)

style = ttk.Style(root)
style.theme_use("clam")

# Frames
frame_left = ttk.Frame(root, padding=10)
frame_left.pack(side="left", fill="y")

frame_right = ttk.Frame(root, padding=10)
frame_right.pack(side="right", expand=True, fill="both")

# --- Left: entrada e controles ---
ttk.Label(frame_left, text="Orçamento Inicial (R$)").pack(anchor="w")
salario_var = tk.StringVar()
entry_salario = ttk.Entry(frame_left, textvariable=salario_var, width=18)
entry_salario.pack(anchor="w", pady=4)
def_def_sal = ttk.Button(frame_left, text="Definir/Atualizar", width=18)
def_def_sal.pack(anchor="w", pady=4)

ttk.Separator(frame_left, orient="horizontal").pack(fill="x", pady=8)

ttk.Label(frame_left, text="Registrar Gasto").pack(anchor="w", pady=(2,0))
entry_desc = ttk.Entry(frame_left, width=28)
entry_desc.insert(0, "Descrição")
entry_desc.bind("<FocusIn>", lambda e: entry_desc.delete(0, tk.END) if entry_desc.get()=="Descrição" else None)
entry_desc.pack(anchor="w", pady=4)

frame_val = ttk.Frame(frame_left)
frame_val.pack(anchor="w")
ttk.Label(frame_val, text="Valor R$").grid(row=0, column=0, padx=(0,6))
entry_valor = ttk.Entry(frame_val, width=12)
entry_valor.grid(row=0, column=1)

ttk.Label(frame_val, text="Data").grid(row=1, column=0, padx=(0,6), pady=(6,0))
entry_data = ttk.Entry(frame_val, width=12)
entry_data.insert(0, datetime.now().strftime("%Y-%m-%d"))
entry_data.grid(row=1, column=1, pady=(6,0))

ttk.Label(frame_left, text="Categoria").pack(anchor="w", pady=(8,0))
categoria_var = tk.StringVar()
combo_categoria = ttk.Combobox(frame_left, textvariable=categoria_var, values=[], width=26)
combo_categoria.pack(anchor="w", pady=4)
combo_categoria.set("Geral")

recorrente_var = tk.BooleanVar()
ttk.Checkbutton(frame_left, text="Marcar como recorrente (mensal)", variable=recorrente_var).pack(anchor="w", pady=4)

ttk.Button(frame_left, text="Registrar Gasto", command=lambda: app_add_gasto()).pack(anchor="w", pady=6)

ttk.Separator(frame_left, orient="horizontal").pack(fill="x", pady=8)

ttk.Label(frame_left, text="Orçamento por Categoria").pack(anchor="w")
entry_cat_name = ttk.Entry(frame_left, width=20)
entry_cat_name.pack(anchor="w", pady=4)
entry_cat_value = ttk.Entry(frame_left, width=20)
entry_cat_value.pack(anchor="w", pady=(0,6))
ttk.Button(frame_left, text="Definir Orçamento Categoria", command=lambda: app_definir_orc_categoria()).pack(anchor="w")

ttk.Separator(frame_left, orient="horizontal").pack(fill="x", pady=8)
ttk.Button(frame_left, text="Aplicar Recorrentes", command=lambda: aplicar_recorrentes(True)).pack(fill="x", pady=4)
ttk.Button(frame_left, text="Backup (salvar)", command=fazer_backup).pack(fill="x", pady=4)
ttk.Button(frame_left, text="Importar JSON", command=lambda: app_importar()).pack(fill="x", pady=4)
ttk.Button(frame_left, text="Importar CSV", command=lambda: importar_csv()).pack(fill="x", pady=4)
ttk.Button(frame_left, text="Exportar CSV", command=lambda: app_export_csv()).pack(fill="x", pady=4)
ttk.Button(frame_left, text="Sair", command=root.destroy).pack(fill="x", pady=14)

# --- Right: lista, filtros e resumo ---
top_right = ttk.Frame(frame_right)
top_right.pack(fill="x")

ttk.Label(top_right, text="Filtros:").grid(row=0, column=0, sticky="w")
mes_var = tk.StringVar()
ano_var = tk.StringVar()
combo_mes = ttk.Combobox(top_right, textvariable=mes_var, values=[""]+[str(i) for i in range(1,13)], width=6)
combo_mes.grid(row=0, column=1, padx=6)
combo_ano = ttk.Combobox(top_right, textvariable=ano_var, values=[""]+[str(y) for y in range(datetime.now().year-5, datetime.now().year+2)], width=8)
combo_ano.grid(row=0, column=2, padx=6)
filtro_cat_var = tk.StringVar()
combo_fil_cat = ttk.Combobox(top_right, textvariable=filtro_cat_var, values=[], width=16)
combo_fil_cat.grid(row=0, column=3, padx=6)

ttk.Label(top_right, text="Pesquisar").grid(row=0, column=4, padx=(12,2))
search_var = tk.StringVar()
entry_search = ttk.Entry(top_right, textvariable=search_var, width=20)
entry_search.grid(row=0, column=5, padx=2)

ttk.Button(top_right, text="Aplicar Filtro", command=lambda: app_refresh()).grid(row=0, column=6, padx=6)
ttk.Button(top_right, text="Limpar Filtro", command=lambda: (mes_var.set(""), ano_var.set(""), filtro_cat_var.set(""), search_var.set(""), app_refresh())).grid(row=0, column=7)

# Treeview de gastos
cols = ("#","data","categoria","descricao","valor")
tree = ttk.Treeview(frame_right, columns=cols, show="headings", selectmode="browse")
for c in cols:
    tree.heading(c, text=c.capitalize(), command=lambda _c=c: sort_treeview(_c, False))
    tree.column(c, anchor="center")
tree.pack(expand=True, fill="both", pady=(8,6))

frame_tree_btns = ttk.Frame(frame_right)
frame_tree_btns.pack(fill="x")
ttk.Button(frame_tree_btns, text="Excluir Selecionado", command=lambda: app_excluir_selecionado()).pack(side="left", padx=4)
ttk.Button(frame_tree_btns, text="Ver Resumo", command=lambda: app_mostrar_resumo()).pack(side="left", padx=4)
ttk.Button(frame_tree_btns, text="Editar Selecionado", command=lambda: app_editar_selecionado()).pack(side="left", padx=4)
ttk.Button(frame_tree_btns, text="Desfazer (Ctrl+Z)", command=lambda: app_undo()).pack(side="left", padx=4)
ttk.Button(frame_tree_btns, text="Gráfico (Matplotlib)", command=lambda: mostrar_grafico_matplotlib()).pack(side="left", padx=4)

# Resumo e gráfico simples
frame_resumo = ttk.LabelFrame(frame_right, text="Resumo")
frame_resumo.pack(fill="both", pady=8)

label_resumo = ttk.Label(frame_resumo, text="", justify="left")
label_resumo.pack(anchor="nw", padx=8, pady=6)

canvas_chart = tk.Canvas(frame_resumo, height=140)
canvas_chart.pack(fill="x", padx=8, pady=(0,8))

# ---------- UI Functions ----------
def app_load():
    aplicar_recorrentes(show_msg=False)  # aplicar automaticamente ao abrir (silencioso)
    dados = carregar_gastos()
    salario_var.set(f"{dados.get('orcamento_inicial',0):.2f}" if dados.get('orcamento_inicial') else "")
    cats = set(dados.get("orcamentos_categoria", {}).keys()) | {g.get("categoria","Geral") for g in dados.get("gastos",[])}
    lista_cats = sorted([c for c in cats if c])
    combo_categoria['values'] = lista_cats
    combo_fil_cat['values'] = [""] + lista_cats
    combo_categoria.set(combo_categoria.get() or "Geral")
    app_refresh()

def adjust_column_widths():
    font = tkfont.Font()
    for col in cols:
        maxw = font.measure(tree.heading(col)['text'])
        for iid in tree.get_children():
            val = tree.set(iid, col) or ""
            w = font.measure(str(val))
            if w > maxw:
                maxw = w
        tree.column(col, width=max(60, maxw + 16))

def app_refresh():
    tree.delete(*tree.get_children())
    dados = carregar_gastos()
    mes = mes_var.get()
    ano = ano_var.get()
    catf = filtro_cat_var.get()
    term = search_var.get().strip().lower()
    gastos = dados["gastos"]
    if mes and ano:
        inicio = f"{int(ano)}-{int(mes):02d}-01"
        fim_date = (datetime(int(ano), int(mes), 1) + timedelta(days=31)).replace(day=1) - timedelta(days=1)
        fim = fim_date.strftime("%Y-%m-%d")
        gastos = [g for g in gastos if inicio <= g["data"] <= fim]
    if catf:
        gastos = [g for g in gastos if g.get("categoria","Geral").lower() == catf.lower()]
    if term:
        gastos = [g for g in gastos if term in g.get("descricao","").lower() or term in g.get("categoria","").lower()]
    gastos_sorted = sorted(gastos, key=lambda x: x["data"], reverse=True)
    for i,g in enumerate(gastos_sorted,1):
        tree.insert("", "end", values=(i, g["data"], g.get("categoria","Geral"), g["descricao"], f"R$ {g['valor']:.2f}"))
    adjust_column_widths()
    app_mostrar_resumo(update_only=True)

def app_add_gasto():
    desc = entry_desc.get().strip()
    if not desc:
        messagebox.showerror("Erro", "Descrição obrigatória.")
        return
    valor = safe_float(entry_valor.get())
    if valor is None:
        messagebox.showerror("Erro", "Valor inválido.")
        return
    data_raw = entry_data.get().strip()
    data = parse_date_to_iso(data_raw) or None
    if not data:
        messagebox.showerror("Erro", "Data inválida. Use YYYY-MM-DD ou DD/MM/YYYY.")
        return
    categoria = categoria_var.get().strip() or "Geral"
    recorrente = recorrente_var.get()
    dados = carregar_gastos()
    gasto = {"id": str(uuid.uuid4()), "descricao": desc, "valor": round(valor,2), "data": data, "categoria": categoria}
    dados["gastos"].append(gasto)
    if recorrente:
        rec = {"descricao": desc, "valor": round(valor,2), "dia": int(data.split("-")[2]), "categoria": categoria, "ultima_geracao": data}
        dados.setdefault("recorrentes", []).append(rec)
    salvar_gastos(dados)
    entry_desc.delete(0, tk.END)
    entry_valor.delete(0, tk.END)
    recorrente_var.set(False)
    app_refresh()
    checar_alerta_categoria(categoria)
    messagebox.showinfo("Sucesso", "Gasto registrado.")

def app_excluir_selecionado():
    sel = tree.selection()
    if not sel:
        messagebox.showwarning("Excluir", "Selecione um gasto.")
        return
    idx = tree.index(sel[0])
    dados = carregar_gastos()
    mes = mes_var.get(); ano = ano_var.get(); catf = filtro_cat_var.get(); term = search_var.get().strip().lower()
    gastos = dados["gastos"]
    if mes and ano:
        inicio = f"{int(ano)}-{int(mes):02d}-01"
        fim_date = (datetime(int(ano), int(mes), 1) + timedelta(days=31)).replace(day=1) - timedelta(days=1)
        fim = fim_date.strftime("%Y-%m-%d")
        gastos = [g for g in gastos if inicio <= g["data"] <= fim]
    if catf:
        gastos = [g for g in gastos if g.get("categoria","Geral").lower() == catf.lower()]
    if term:
        gastos = [g for g in gastos if term in g.get("descricao","").lower() or term in g.get("categoria","").lower()]
    gastos_sorted = sorted(gastos, key=lambda x: x["data"], reverse=True)
    if 0 <= idx < len(gastos_sorted):
        gasto = gastos_sorted[idx]
        # remover item correspondente do dados["gastos"] por id preferencialmente
        for i, g in enumerate(dados["gastos"]):
            if g.get("id") == gasto.get("id") or (g["descricao"]==gasto["descricao"] and g["data"]==gasto["data"] and abs(g["valor"]-gasto["valor"])<0.01):
                removed = dados["gastos"].pop(i)
                salvar_gastos(dados)
                # push to undo stack
                _last_deleted.append({"index": i, "item": removed})
                app_refresh()
                messagebox.showinfo("Excluir", f"Gasto '{gasto['descricao']}' excluído.")
                return
    messagebox.showerror("Erro", "Não foi possível excluir o gasto selecionado.")

def app_undo():
    if not _last_deleted:
        messagebox.showinfo("Desfazer", "Nada para desfazer.")
        return
    dados = carregar_gastos()
    last = _last_deleted.pop()
    idx = last.get("index", len(dados["gastos"]))
    item = last.get("item")
    if item:
        # re-inserir na posição original se possível
        idx = min(idx, len(dados["gastos"]))
        dados["gastos"].insert(idx, item)
        salvar_gastos(dados)
        app_refresh()
        messagebox.showinfo("Desfazer", f"Gasto '{item.get('descricao')}' restaurado.")

def app_definir_orc_categoria():
    nome = entry_cat_name.get().strip()
    val = safe_float(entry_cat_value.get())
    if not nome or val is None:
        messagebox.showerror("Erro", "Categoria ou valor inválido.")
        return
    dados = carregar_gastos()
    dados.setdefault("orcamentos_categoria", {})[nome] = round(val,2)
    salvar_gastos(dados)
    app_load()
    messagebox.showinfo("OK", f"Orçamento para '{nome}' salvo.")

def app_set_salario():
    val = safe_float(salario_var.get())
    if val is None:
        messagebox.showerror("Erro", "Salário inválido.")
        return
    dados = carregar_gastos()
    dados["orcamento_inicial"] = round(val,2)
    salvar_gastos(dados)
    app_refresh()
    messagebox.showinfo("OK", "Orçamento inicial atualizado.")

def app_importar():
    path = filedialog.askopenfilename(title="Importar JSON", filetypes=[("JSON","*.json"),("All","*.*")])
    if path:
        importar_arquivo(path)

def app_export_csv():
    path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV","*.csv")], initialfile="gastos_export.csv")
    if path:
        exportar_csv(path)

def app_mostrar_resumo(update_only=False):
    dados = carregar_gastos()
    mes = mes_var.get(); ano = ano_var.get()
    gastos = dados["gastos"]
    if mes and ano:
        inicio = f"{int(ano)}-{int(mes):02d}-01"
        fim_date = (datetime(int(ano), int(mes), 1) + timedelta(days=31)).replace(day=1) - timedelta(days=1)
        fim = fim_date.strftime("%Y-%m-%d")
        gastos = [g for g in gastos if inicio <= g["data"] <= fim]
    total_gasto = sum(g["valor"] for g in gastos)
    orc = dados.get("orcamento_inicial",0.0)
    texto = f"Orçamento Inicial: R$ {orc:.2f}\nTotal Gasto: R$ {total_gasto:.2f}\nSaldo: R$ {orc - total_gasto:.2f}\n"
    por_cat = defaultdict(float)
    for g in gastos:
        por_cat[g.get("categoria","Geral")] += g["valor"]
    texto += "\nGastos por categoria:\n"
    for c,v in sorted(por_cat.items(), key=lambda x: x[1], reverse=True):
        texto += f" - {c}: R$ {v:.2f}\n"
    label_resumo.config(text=texto)
    desenhar_grafico(por_cat)

def desenhar_grafico(dados_cat):
    canvas_chart.delete("all")
    if not dados_cat:
        canvas_chart.create_text(10,10, anchor="nw", text="(sem dados)", fill="#444")
        return
    largura = canvas_chart.winfo_width() or 800
    padding = 10
    total = sum(dados_cat.values())
    max_bar = largura - 2*padding
    colors = ["#4e79a7","#f28e2b","#e15759","#76b7b2","#59a14f","#edc949","#af7aa1","#ff9da7"]
    y = padding
    i = 0
    for cat, val in sorted(dados_cat.items(), key=lambda x: x[1], reverse=True):
        propor = int((val/total) * max_bar) if total>0 else 0
        color = colors[i % len(colors)]
        canvas_chart.create_rectangle(padding, y, padding+propor, y+24, fill=color, outline="")
        canvas_chart.create_text(padding+propor+8, y+12, anchor="w", text=f"{cat} R$ {val:.2f}", fill="#222")
        y += 30
        i += 1

def checar_alerta_categoria(categoria):
    dados = carregar_gastos()
    orc_cat = dados.get("orcamentos_categoria", {})
    if categoria in orc_cat:
        hoje = datetime.now()
        mes, ano = hoje.month, hoje.year
        inicio = f"{ano}-{mes:02d}-01"
        fim_date = (datetime(ano, mes, 1) + timedelta(days=31)).replace(day=1) - timedelta(days=1)
        fim = fim_date.strftime("%Y-%m-%d")
        gasto_cat = sum(g["valor"] for g in dados["gastos"] if inicio <= g["data"] <= fim and g.get("categoria","Geral")==categoria)
        if gasto_cat > orc_cat[categoria]:
            messagebox.showwarning("Alerta Orçamento", f"Categoria '{categoria}' estourou o orçamento:\n{gasto_cat:.2f} > {orc_cat[categoria]:.2f}")

# ---------- Edit ----------
def app_editar_selecionado():
    sel = tree.selection()
    if not sel:
        messagebox.showwarning("Editar", "Selecione um gasto.")
        return
    idx = tree.index(sel[0])
    dados = carregar_gastos()
    mes = mes_var.get(); ano = ano_var.get(); catf = filtro_cat_var.get(); term = search_var.get().strip().lower()
    gastos = dados["gastos"]
    if mes and ano:
        inicio = f"{int(ano)}-{int(mes):02d}-01"
        fim_date = (datetime(int(ano), int(mes), 1) + timedelta(days=31)).replace(day=1) - timedelta(days=1)
        fim = fim_date.strftime("%Y-%m-%d")
        gastos = [g for g in gastos if inicio <= g["data"] <= fim]
    if catf:
        gastos = [g for g in gastos if g.get("categoria","Geral").lower() == catf.lower()]
    if term:
        gastos = [g for g in gastos if term in g.get("descricao","").lower() or term in g.get("categoria","").lower()]
    gastos_sorted = sorted(gastos, key=lambda x: x["data"], reverse=True)
    if not (0 <= idx < len(gastos_sorted)):
        messagebox.showerror("Erro", "Item não encontrado.")
        return
    gasto = gastos_sorted[idx]
    novo_desc = simpledialog.askstring("Editar", "Descrição:", initialvalue=gasto["descricao"])
    if novo_desc is None:
        return
    novo_val = simpledialog.askstring("Editar", "Valor (R$):", initialvalue=f"{gasto['valor']:.2f}")
    if novo_val is None:
        return
    nv = safe_float(novo_val)
    if nv is None:
        messagebox.showerror("Erro", "Valor inválido.")
        return
    nova_data_raw = simpledialog.askstring("Editar", "Data (YYYY-MM-DD ou DD/MM/YYYY):", initialvalue=gasto["data"])
    if nova_data_raw is None:
        return
    nova_data = parse_date_to_iso(nova_data_raw)
    if not nova_data:
        messagebox.showerror("Erro", "Data inválida.")
        return
    # atualizar no dados originais por id
    for i, g in enumerate(dados["gastos"]):
        if g.get("id") == gasto.get("id"):
            dados["gastos"][i]["descricao"] = novo_desc
            dados["gastos"][i]["valor"] = round(nv,2)
            dados["gastos"][i]["data"] = nova_data
            salvar_gastos(dados)
            app_refresh()
            messagebox.showinfo("OK", "Gasto atualizado.")
            return
    messagebox.showerror("Erro", "Falha ao atualizar.")

# ---------- Ordenação ----------
def sort_treeview(col, reverse):
    # obter dados atuais no view e ordenar
    data = [(tree.set(k, col), k) for k in tree.get_children("")]
    # se coluna numérica (# ou valor), converter
    def keyfunc(x):
        v = x[0]
        if col == "#" :
            try: return int(v)
            except: return 0
        if col == "valor":
            try:
                return float(str(v).replace("R$","").replace(",","").strip())
            except:
                return 0.0
        return v.lower() if isinstance(v, str) else v
    data.sort(key=keyfunc, reverse=reverse)
    for index, (val, k) in enumerate(data):
        tree.move(k, '', index)
    # alternar próxima chamada
    tree.heading(col, command=lambda: sort_treeview(col, not reverse))

# ---------- Matplotlib gráfico modal ----------
def mostrar_grafico_matplotlib():
    try:
        import matplotlib.pyplot as plt
    except Exception:
        messagebox.showerror("Matplotlib", "Matplotlib não instalado. Instale com: pip install matplotlib")
        return
    dados = carregar_gastos()
    mes = mes_var.get(); ano = ano_var.get()
    gastos = dados["gastos"]
    if mes and ano:
        inicio = f"{int(ano)}-{int(mes):02d}-01"
        fim_date = (datetime(int(ano), int(mes), 1) + timedelta(days=31)).replace(day=1) - timedelta(days=1)
        fim = fim_date.strftime("%Y-%m-%d")
        gastos = [g for g in gastos if inicio <= g["data"] <= fim]
    por_cat = defaultdict(float)
    for g in gastos:
        por_cat[g.get("categoria","Geral")] += g["valor"]
    if not por_cat:
        messagebox.showinfo("Gráfico", "Sem dados para mostrar.")
        return
    labels = list(por_cat.keys())
    sizes = list(por_cat.values())
    fig, ax = plt.subplots()
    ax.pie(sizes, labels=labels, autopct='%1.1f%%', startangle=90)
    ax.axis('equal')
    title = "Gastos por categoria"
    if mes and ano:
        title += f" - {mes}/{ano}"
    plt.title(title)
    plt.show()

# ---------- Shortcuts / Binds ----------
def on_key(event):
    if (event.state & 0x4) and event.keysym.lower() == 'z':  # Ctrl+Z
        app_undo()

root.bind_all("<Key>", on_key)
canvas_chart.bind("<Configure>", lambda e: app_mostrar_resumo(update_only=True))

# Bind buttons
def_def_sal.config(command=app_set_salario)

# Inicialização
root.after(200, app_load)
root.mainloop()
