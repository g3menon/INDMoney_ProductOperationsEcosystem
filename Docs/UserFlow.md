# User flow (source)

This file is the concise product narrative. The full system design, including tab behavior and alignment with these flows, lives in `Docs/Architecture.md` under **User flows (authoritative product behavior)**.

## Product (PM)

A PM opens the dashboard and can subscribe to the weekly pulse email. The same pulse is visible on the dashboard. On subscribing, the user receives an email with the current pulse and will then receive subsequent weekly pulses every **Monday 10:00 a.m. IST**. The dashboard should show clear feedback when subscription or sends change. The pulse area should also show **analytics** on the main issues users are booking advisor appointments for—derived from chat / booking context (including the voice or chat brief that supports the email), not from Google Sheets as source of truth.

**Fee explainer scope:** the structured **fee explainer** experience (e.g. six-bullet fee answers grounded in sources) is **not** a Product-tab or weekly-email feature. PM surfaces carry **pulse themes, quotes, actions, and analytics**—not customer-style fee Q&A.

## Customer

Customers use the chatbot for mutual fund Q&A from the approved **source list**, and may use **voice** as well. They can use **typing**, **pre-proposed prompt buttons**, and **voice** in the same session (not mutually exclusive). From any mode they can:

- ask mutual fund questions;
- ask fee-explanation questions;
- book an appointment with a financial advisor; or
- cancel an appointment using their **booking ID**.

Prepopulated prompts may be MF/source-list–driven, or nudge users to book for issues that show up in **weekly pulse inferences**. Chat history is available. **Hybrid** prompts (MF + fee in one message) must be **fully** answered. After the customer finishes booking, they receive a **copyable** booking ID in chat.

## Advisor

The advisor can **approve** the booking so the **customer** receives the **booking confirmation email** only after that approval. The advisor sees an overview of **upcoming** slots and **pending** confirmations, each with **booking ID** as booked from the customer path. Each item should carry a **summary of the customer’s chat** for context. The advisor may review the **proposed confirmation email**, **booking ID**, and a **summary of the conversation** before the appointment, when the product surfaces them.

**Fee explainer scope:** when the customer’s chat included fee questions, **source-backed fee explanation** may appear in **advisor-only** contexts (e.g. confirmation preview or advisor notes)—using the same policy constraints as Customer chat, not as a generic dashboard tutorial.
