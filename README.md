# 💰 Gastos App — Gerenciador Pessoal de Finanças

![Status](https://img.shields.io/badge/status-ativo-brightgreen)
![Versão](https://img.shields.io/badge/versão-1.0-blue)
![Licença](https://img.shields.io/badge/licença-MIT-yellow)
![Python](https://img.shields.io/badge/python-3.x-blue?logo=python)
![Tkinter](https://img.shields.io/badge/Tkinter-GUI-orange)

## 📖 Introdução
O **Gastos App** é uma aplicação desktop desenvolvida em **Python (Tkinter)** para auxiliar no **controle de finanças pessoais**.  
Ele permite registrar despesas, definir orçamentos, acompanhar relatórios e visualizar gráficos interativos, tudo de forma simples e prática.  

O objetivo é ajudar qualquer pessoa a ter mais controle sobre **entradas e saídas de dinheiro**, organizar seus gastos por categoria e tomar melhores decisões financeiras.  

---

## ✨ Funcionalidades principais
- 📝 **Registrar gastos** com descrição, valor, data e categoria  
- 📂 **Gerenciamento por categorias** e orçamentos específicos  
- 🔁 **Despesas recorrentes mensais**  
- 📊 **Relatórios e gráficos** de gastos por categoria  
- 📥 **Importar dados** em JSON ou CSV  
- 📤 **Exportar dados** em CSV  
- 💾 **Backup automático** dos dados  
- ↩️ **Desfazer exclusões** (atalho Ctrl+Z)  
- 🔍 **Filtros de busca** por data, categoria e descrição  
- ✏️ **Edição de registros existentes**  
- ⚠️ **Alertas automáticos** quando uma categoria ultrapassa o orçamento definido  

---

## 🛠️ Tecnologias usadas
- **Python 3.x**  
- **Tkinter** → interface gráfica  
- **JSON / CSV** → armazenamento e importação/exportação  
- **Matplotlib** → geração de gráficos (opcional)  
- **UUID** → identificação única de registros  
- **Deque** → pilha de desfazer (undo)  

---

## ⚙️ Instalação
1. Clone este repositório:
   ```bash
   git clone https://github.com/seu-usuario/gastos-app.git
   cd gastos-app
