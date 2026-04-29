# UI — Groww Product Operations Ecosystem

**Canonical URLs, fund list, Play Store rules, and reference design links** live in **`Deliverables/Resources.md`**. Keep UI copy and engineering in sync with that file. Also use some Groww branding colors so the design stays consistent.

## Reference UI (visual inspiration)

- **Product** tab / pulse + email inspiration: https://dribbble.com/shots/26857590-CallAI-AI-Voice-Assistants-Dashboard-Design  
- **Customer** chat: https://dribbble.com/shots/26057790-Ultima-AI-Dashboard-Your-Smart-Chat-Partner and https://dribbble.com/shots/26756293-Voice-AI-Automation-Dashboard  
- **Advisor**: https://dribbble.com/shots/25680703-Voice-AI-Agent-Configurations  

## Information architecture

Design is **responsive** for mobile and web.

### Three tabs (badges, cues, cross-tab consistency)

#### Customer

- **Chatbot**
  - **Input:** voice, preloaded chips, typing (same session).
  - **Conversation** (always show **hyperlinked** source URLs from approved corpus):
    - **Mutual fund:** factual answer from approved sources; out-of-scope → concise redirect / safe prompt.
    - **Fee explainer:** **six concise bullets** + sources + “last checked” where applicable (**Customer surface**).
    - **Hybrid (MF + fee):** MF portion as above + **six concise fee bullets**; both parts answered in one turn.
  - Responses are **copyable**.
  - **Chat history**; **Start new chat**.

#### Advisor

- Appointment **approval / rejection**; booking ID, date/time, topic; appointment logs.
- **Proposed confirmation email** preview (approval-gated send).
- **Disclaimer** (informational, not advice).

#### Product (PM)

- **Pulse dashboard** (reviews-forward): top metrics (reviews count, average rating, top themes), theme summaries, quotes, suggested PM actions, **classified reviews table** with CSV download (filters: **Phone / Chromebook / Tablet** per `Deliverables/Resources.md` collection fields).
- **Weekly pulse email:** mirrors **dashboard pulse content** (themes, quotes, actions, link to dashboard)—**does not** include the Customer-style **six-bullet fee explainer** block; fee education stays on **Customer** (and **Advisor** booking-related previews only), per `Docs/UserFlow.md`.
