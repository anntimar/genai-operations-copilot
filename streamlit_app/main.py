import os
from datetime import date

import httpx
import streamlit as st

API = os.getenv("API_URL", "http://localhost:8000")
TASKS = {
    "Consultar": "search",
    "Comparar": "compare",
    "Resumir ocorrência": "incident",
    "Investigar divergências": "contradictions",
    "Próximos passos": "next_steps",
    "Solicitar aprovação": "approval",
}


def request(method, path, **kwargs):
    try:
        response = httpx.request(method, API + path, timeout=45, **kwargs)
        response.raise_for_status()
        return response.json()
    except httpx.HTTPStatusError as error:
        st.error(f"API retornou {error.response.status_code}. {error.response.text}")
    except httpx.RequestError:
        st.error("API indisponível.")
    return None


st.set_page_config(page_title="Copiloto de Operações", page_icon="📋")
st.title("Copiloto de Operações")
st.caption("Central de procedimentos da Rota Nuvem, marketplace fictício.")
chat, library = st.tabs(["Consulta", "Documentos"])
with library:
    with st.form("upload"):
        file = st.file_uploader("Procedimento", type=["pdf", "txt", "md"])
        category = st.text_input("Categoria", max_chars=80)
        effective_date = st.date_input("Data de vigência")
        if st.form_submit_button("Enviar") and file and category:
            result = request(
                "POST",
                "/documents/upload",
                files={"file": (file.name, file.getvalue())},
                data={
                    "category": category,
                    "effective_date": effective_date.isoformat(),
                },
            )
            if result:
                st.success(f"Documento indexado: {result['name']}")
    documents = request("GET", "/documents") or []
    if documents:
        st.dataframe(documents, hide_index=True)

with chat:
    with st.form("ask"):
        question = st.text_area("Pergunta ou relato", max_chars=4000)
        task = st.selectbox("Tarefa", list(TASKS))
        with st.expander("Filtros"):
            names = {doc["id"]: doc["name"] for doc in documents}
            document = st.selectbox(
                "Documento",
                [None, *names],
                format_func=lambda key: names.get(key, "Todos"),
            )
            selected_category = st.selectbox(
                "Categoria", [None, *sorted({doc["category"] for doc in documents})]
            )
            since = st.date_input("A partir de", value=None, min_value=date(2000, 1, 1))
            until = st.date_input("Até", value=None, min_value=date(2000, 1, 1))
        if st.form_submit_button("Consultar") and question.strip():
            turn = request(
                "POST",
                "/chat/ask",
                json={
                    "question": question,
                    "task": TASKS[task],
                    "session_id": st.session_state.get("session"),
                    "document_id": document,
                    "category": selected_category,
                    "since": since.isoformat() if since else None,
                    "until": until.isoformat() if until else None,
                },
            )
            if turn:
                st.session_state.session = turn["session_id"]
    session_id = st.text_input(
        "ID da sessão", value=st.session_state.get("session", "")
    )
    active = st.session_state.get("session") or session_id.strip()
    if st.button("Abrir sessão") and session_id.strip():
        st.session_state.session = session_id.strip()
        active = session_id.strip()
    if active:
        st.caption(f"Sessão ativa: {active}")
    turns = request("GET", f"/chat/sessions/{active}") if active else []
    for turn in reversed(turns or []):
        with st.chat_message("user"):
            st.text(turn["question"])
        with st.chat_message("assistant"):
            st.text(turn["answer"])
            for index, source in enumerate(turn["citations"], 1):
                with st.expander(f"[{index}] {source['name']} · p. {source['page']}"):
                    st.text(source["excerpt"])
                    st.caption(f"{source['category']} · {source['date']}")
            st.caption(f"{turn['latency_ms']} ms · {' → '.join(turn['trace'])}")
            with st.form(f"feedback-{turn['id']}"):
                positive = st.form_submit_button("Útil")
                negative = st.form_submit_button("Pouco útil")
                if (positive or negative) and request(
                    "POST",
                    "/feedback",
                    json={"turn_id": turn["id"], "positive": positive},
                ):
                    st.success("Feedback registrado.")
            if turn["approval"]:
                st.write(f"Revisão: {turn['approval']}")
            if turn["approval"] == "pending":
                with st.form(f"approval-{turn['id']}"):
                    key = st.text_input("Chave do revisor", type="password")
                    approve = st.form_submit_button("Aprovar")
                    reject = st.form_submit_button("Rejeitar")
                    if (approve or reject) and request(
                        "POST",
                        f"/approvals/{turn['id']}",
                        json={"approve": approve},
                        headers={"X-Approval-Key": key},
                    ):
                        st.rerun()
