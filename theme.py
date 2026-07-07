# -*- coding: utf-8 -*-
"""Tema visual do Beer Game: paletas claro/escuro, fontes e estilos ttk."""
import tkinter as tk
from tkinter import ttk

PALETAS = {
    "claro": dict(
        bg="#f6f1e7", card="#ffffff", header="#2f2013", header_fg="#f8edd8",
        texto="#2b2620", suave="#7a7265", accent="#c07f1f", accent_fg="#ffffff",
        borda="#d8cfc0", canvas="#fffdf8", grade="#ece5d6", eixo="#9a9183",
        ok="#1e8e3e", alerta="#c98f06", perigo="#c5221f",
        chip_pedido="#4a78a8", sombra_neg="#f6d3d2",
    ),
    "escuro": dict(
        bg="#211e19", card="#2d2a23", header="#14110c", header_fg="#f0e2c8",
        texto="#ece5d8", suave="#a89f8e", accent="#e3a635", accent_fg="#241b07",
        borda="#403b31", canvas="#262320", grade="#383328", eixo="#8d8472",
        ok="#5dbb6c", alerta="#e5b94e", perigo="#e2655f",
        chip_pedido="#6f97c4", sombra_neg="#4a2b29",
    ),
}

atual = "claro"
_ouvintes = []  # [(widget, callback)]

# escala de fonte: índice em ESCALAS (controle no cabeçalho A- / A+)
ESCALAS = [0.85, 1.0, 1.15, 1.30, 1.5, 1.75]
_i_escala = 1

_TAM_BASE = {            # tamanhos de referência (escala 1.0)
    "titulo": 19, "h2": 12, "num": 20,
    "rotulo": 9, "rotulo_b": 9, "mini": 8, "botao": 10,
}


def cores() -> dict:
    return PALETAS[atual]


def escala() -> float:
    return ESCALAS[_i_escala]


def _tam(chave) -> int:
    return max(6, round(_TAM_BASE[chave] * ESCALAS[_i_escala]))


def fontes() -> dict:
    base = "Segoe UI"
    return {
        "titulo": (base, _tam("titulo"), "bold"),
        "h2": (base, _tam("h2"), "bold"),
        "num": (base, _tam("num"), "bold"),
        "rotulo": (base, _tam("rotulo")),
        "rotulo_b": (base, _tam("rotulo_b"), "bold"),
        "mini": (base, _tam("mini")),
        "botao": (base, _tam("botao")),
    }


def pode_aumentar() -> bool:
    return _i_escala < len(ESCALAS) - 1


def pode_diminuir() -> bool:
    return _i_escala > 0


def mudar_escala(root, delta: int):
    """delta = +1 (aumenta) ou -1 (diminui). Reaplica tema e notifica."""
    global _i_escala
    novo = min(len(ESCALAS) - 1, max(0, _i_escala + delta))
    if novo == _i_escala:
        return False
    _i_escala = novo
    aplicar(root)
    _notificar()
    return True


def registrar(widget, callback):
    """Widget será avisado quando o tema mudar (e removido ao ser destruído)."""
    par = (widget, callback)
    _ouvintes.append(par)
    widget.bind("<Destroy>",
                lambda e, p=par: p in _ouvintes and _ouvintes.remove(p), add="+")


def _notificar():
    for w, cb in list(_ouvintes):
        try:
            if w.winfo_exists():
                cb()
        except tk.TclError:
            pass


def aplicar(root):
    c, f = cores(), fontes()
    st = ttk.Style(root)
    try:
        st.theme_use("clam")
    except tk.TclError:
        pass
    st.configure(".", background=c["bg"], foreground=c["texto"],
                 bordercolor=c["borda"], lightcolor=c["bg"], darkcolor=c["bg"],
                 troughcolor=c["card"], font=f["rotulo"])
    st.configure("TFrame", background=c["bg"])
    st.configure("Card.TFrame", background=c["card"])
    st.configure("TLabel", background=c["bg"], foreground=c["texto"])
    st.configure("Card.TLabel", background=c["card"], foreground=c["texto"])
    st.configure("Suave.TLabel", background=c["bg"], foreground=c["suave"])
    st.configure("H2.TLabel", background=c["bg"], foreground=c["texto"], font=f["h2"])
    st.configure("Titulo.TLabel", background=c["bg"], foreground=c["texto"],
                 font=f["titulo"])
    st.configure("TButton", font=f["botao"], background=c["card"],
                 foreground=c["texto"], padding=(10, 5), borderwidth=1)
    st.map("TButton", background=[("active", c["accent"])],
           foreground=[("active", c["accent_fg"])])
    st.configure("Accent.TButton", background=c["accent"],
                 foreground=c["accent_fg"], font=f["botao"])
    st.map("Accent.TButton", background=[("active", c["header"])],
           foreground=[("active", c["header_fg"])])
    st.configure("TLabelframe", background=c["bg"], bordercolor=c["borda"])
    st.configure("TLabelframe.Label", background=c["bg"], foreground=c["suave"],
                 font=f["rotulo_b"])
    st.configure("Treeview", background=c["card"], fieldbackground=c["card"],
                 foreground=c["texto"], rowheight=round(24 * escala()),
                 bordercolor=c["borda"])
    st.configure("Treeview.Heading", background=c["bg"], foreground=c["texto"],
                 font=f["rotulo_b"])
    st.map("Treeview", background=[("selected", c["accent"])],
           foreground=[("selected", c["accent_fg"])])
    for w in ("TEntry", "TSpinbox", "TCombobox"):
        st.configure(w, fieldbackground=c["card"], foreground=c["texto"],
                     insertcolor=c["texto"], arrowcolor=c["texto"],
                     selectbackground=c["accent"], selectforeground=c["accent_fg"])
    root.option_add("*TCombobox*Listbox.background", c["card"])
    root.option_add("*TCombobox*Listbox.foreground", c["texto"])
    st.configure("TNotebook", background=c["bg"], borderwidth=0)
    st.configure("TNotebook.Tab", background=c["bg"], foreground=c["suave"],
                 padding=(14, 5), font=f["rotulo_b"])
    st.map("TNotebook.Tab", background=[("selected", c["card"])],
           foreground=[("selected", c["texto"])])
    st.configure("TSeparator", background=c["borda"])
    root.configure(bg=c["bg"])


def alternar(root):
    global atual
    atual = "escuro" if atual == "claro" else "claro"
    aplicar(root)
    _notificar()
