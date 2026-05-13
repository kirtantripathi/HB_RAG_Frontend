"""
Streamlit chat frontend for the HubBroker RAG API.

Start (requires the FastAPI server running on port 8000):
    streamlit run frontend.py
"""

import re
import uuid

import streamlit as st
import requests
# from ingestion.config import TOP_K_RESULTS

# ── Top K ──────────────────────────────────
top_k = 10

# API_URL = "http://localhost:8000"
API_URL = "https://unsettled-vowed-oink.ngrok-free.dev"

# ── Regex for image placeholders ─────────────
# Matches patterns like: [IMAGE: Some Caption] [image-id: be8e037]
_IMAGE_PATTERN = re.compile(
    r"\[IMAGE:\s*([^\]]+?)\]\s*\[image-id:\s*([a-fA-F0-9]+)\]",
)

def render_answer_with_images(text: str) -> None:
    """Render an LLM answer, replacing image placeholders with actual images."""
    last_end = 0
    for match in _IMAGE_PATTERN.finditer(text):
        # Render any text before this match
        preceding = text[last_end:match.start()].strip()
        if preceding:
            st.markdown(preceding)
        caption = match.group(1).strip()
        image_id = match.group(2).strip()
        image_url = f"{API_URL}/images/{image_id}.png"
        st.image(image_url, caption=caption)
        last_end = match.end()
    # Render any remaining text after the last match
    remaining = text[last_end:].strip()
    if remaining:
        st.markdown(remaining)

# ── Page config ──────────────────────────────

st.set_page_config(
    page_title="HubBroker RAG",
    page_icon="💬",
    layout="centered",
)

# ── Custom CSS ───────────────────────────────

st.markdown("""
<style>
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

  /* Global */
  html, body, [class*="css"] { font-family: 'Inter', sans-serif; }

  /* Hide default Streamlit branding */
  #MainMenu, footer, header { visibility: hidden; }

  /* Chat message tweaks */
  .stChatMessage { border-radius: 12px; }

  /* Sources expander */
  .streamlit-expanderHeader {
    font-size: 0.82rem;
    color: #888;
  }

</style>
""", unsafe_allow_html=True)



# ── Session state ────────────────────────────

if "messages" not in st.session_state:
    st.session_state.messages = []

# Generate a unique thread_id per session for PostgreSQL-backed memory
if "thread_id" not in st.session_state:
    st.session_state.thread_id = str(uuid.uuid4())

# ── Render chat history ──────────────────────

for msg in st.session_state.messages:
    with st.chat_message(msg["role"], avatar="🧑‍💻" if msg["role"] == "user" else "🤖"):
        render_answer_with_images(msg["content"])
        if msg.get("sources"):
            with st.expander(f"📄 {len(msg['sources'])} source(s)"):
                for i, s in enumerate(msg["sources"], 1):
                    heading = f" — {s['heading']}" if s.get("heading") else ""
                    if s.get("article_url"):
                        st.markdown(
                            f"**[{i}]** [{s['heading'] or s['file_name']}]({s['article_url']})  "
                            f"·  _{s['category']}{heading}_"
                        )
                    else:
                        st.markdown(
                            f"**[{i}]** {s['file_name']}  ·  p.{s['page_number']}  "
                            f"·  _{s['category']}{heading}_"
                        )
        if msg.get("meta"):
            st.caption(msg["meta"])

# ── Welcome suggestions (shown when chat is empty) ──

if not st.session_state.messages:
    st.markdown(
        "<h2 style='text-align:center; margin-top:2rem;'>What can I help you with?</h2>"
        "<p style='text-align:center; color:#888;'>Ask anything about HubBroker documentation.</p>",
        unsafe_allow_html=True,
    )
    cols = st.columns(3)
    suggestions = [
        "What is HubBroker?",
        "How do I set up EDI connections?",
        "What file formats does HubBroker support?",
    ]
    for col, q in zip(cols, suggestions):
        if col.button(q, use_container_width=True):
            st.session_state.pending_question = q
            st.rerun()

# ── Handle pending suggestion click ──────────

pending = st.session_state.pop("pending_question", None)

# ── Chat input ───────────────────────────────

prompt = st.chat_input("Ask a question…")
question = pending or prompt

if question:
    # Save user message and show spinner while calling API
    st.session_state.messages.append({"role": "user", "content": question})
    with st.chat_message("user", avatar="🧑‍💻"):
        st.markdown(question)

    # Call API — only show a spinner, no answer rendered here.
    # The answer is saved to session_state and st.rerun() re-renders
    # everything via the history loop, avoiding stale/duplicate content.
    with st.chat_message("assistant", avatar="🤖"):
        with st.spinner("Thinking…"):
            try:
                resp = requests.post(
                    f"{API_URL}/chat",
                    json={
                        "question": question,
                        "top_k": top_k,
                        "thread_id": st.session_state.thread_id,
                    },
                    timeout=120,
                )
                resp.raise_for_status()
                data = resp.json()

                sources = data.get("sources", [])
                rewritten = data.get("rewritten_query", "")
                meta = f"{data['chunks_retrieved']} chunks · {data['model']}"
                if rewritten and rewritten != question:
                    meta += f"  ·  🔄 _{rewritten}_"

                st.session_state.messages.append({
                    "role": "assistant",
                    "content": data["answer"],
                    "sources": sources,
                    "meta": meta,
                })

            except requests.ConnectionError:
                err = "⚠️ Cannot reach the API server. Make sure it's running on port 8000."
                st.session_state.messages.append({"role": "assistant", "content": err})
            except Exception as e:
                err = f"⚠️ Error: {e}"
                st.session_state.messages.append({"role": "assistant", "content": err})

    # Rerun so the history loop renders the new answer cleanly
    st.rerun()
