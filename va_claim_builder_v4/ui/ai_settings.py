import os
import streamlit as st


def render_ai_settings():
    st.subheader("AI Provider Settings")
    mode = st.radio("Analysis mode", ["Single provider with fallback", "Parallel multi-agent consensus"],
                    index=1 if os.getenv("VCB_AI_MODE", "ensemble") == "ensemble" else 0)
    provider = st.selectbox("Primary provider", ["openai", "xai"], index=0 if os.getenv("VCB_AI_PROVIDER", "openai") == "openai" else 1)
    fallback = st.selectbox("Fallback provider", ["none", "openai", "xai"], index=0)
    ensemble = st.multiselect("Independent agents", ["openai", "xai"], default=["openai", "xai"])
    adjudicator = st.selectbox("Disagreement adjudicator", ["none", "openai", "xai"], index=0)
    max_concurrency = st.slider("Maximum concurrent AI requests", 1, 4, 2)
    local_only = st.checkbox("Local-only mode (disables ChatGPT and Grok)", value=os.getenv("VCB_LOCAL_ONLY", "false").lower() == "true")
    redact = st.checkbox("Redact common identifiers before cloud processing", value=True)
    st.caption("ChatGPT and Grok consumer logins are not used directly. Configure separate OpenAI and xAI API keys. Keys are never displayed or written into project files.")
    return {
        "mode": "ensemble" if mode.startswith("Parallel") else "single",
        "provider": provider,
        "fallback": None if fallback == "none" else fallback,
        "ensemble": ensemble,
        "adjudicator": None if adjudicator == "none" else adjudicator,
        "max_concurrency": max_concurrency,
        "local_only": local_only,
        "redact": redact,
    }
