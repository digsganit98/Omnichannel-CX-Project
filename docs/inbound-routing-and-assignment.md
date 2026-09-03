# Inbound routing and assignment — how it works today

Answers to four questions about where customer messages land and who picks them up. Every
statement below was verified against the code and configuration.

---

## 1. When a customer sends an email, whose inbox does it reach?

**One shared support mailbox: `customersupportomnichannelcx@gmail.com`.** It is not any
individual's inbox.

The application polls that mailbox over IMAP every 30 seconds for unread mail, converts each
message into an inbound event, and marks it read on the server so it is not processed twice.
Replies are sent from the same address over SMTP.

The customer emails a support address, not a person.

---

## 2. Who decides which agent is assigned to the email?

**Nobody. There is no individual assignment.**

A ticket is assigned to a **team**, by a static lookup from the classified intent:
`assign_team(intent)` reads a fixed intent-to-team map and falls back to `customer_support`.

There is no assignee field, no per-agent queue, no round-robin, no load balancing, and no way
for an agent to claim a ticket. Every agent with the console open sees the same shared list and
can act on anything in it.

This is a known gap, listed in the production scope document under escalation routing:
*skills-based routing to named queues and individuals, with a named owner per escalation level.*

---

## 3. Two team members have the app open. Who receives an incoming query?

**Both — and that is the problem.**

Each developer runs their **own complete stack**: their own API container, their own SQLite
database, their own graph database. Nothing is shared between them.

With the same configuration on two machines:

| Channel | What actually happens |
|---|---|
| **Email** | Both pollers hit the same Gmail inbox every 30 seconds. **Whoever polls first wins** — it marks the message read, and the other machine never sees it. A race decided by timing |
| **WhatsApp** | Meta delivers the webhook to **one** tunnel URL. Only whoever owns that domain receives it; the other receives nothing |
| **Web chat** | Fully separate — each portal talks only to its own local API |

So this is not two people sharing a queue. It is **two disconnected systems competing for the
same mailbox**, each holding a different half of the conversation history.

**This is a deployment problem, not a defect in the application.**

---

## 4. What changes once it is deployed on AWS?

Deployment fixes the split-brain. It does **not** fix the assignment gap. These are two separate
pieces of work.

**Resolved by deployment**

- One shared database — every agent sees the same tickets, cases and history
- One application behind a load balancer — multiple agents use the same system, not copies of it
- One inbound path — a real webhook endpoint, with no tunnel and no domain contention
- **The email race must be handled explicitly.** With multiple application instances, every
  instance cannot poll the mailbox independently or the same race reappears at scale. The options
  are a single dedicated poller, a push model (managed mail service into a queue), or a lock

**Still to be built, regardless of deployment**

- Assignment to individuals, and per-agent queues
- A claim or lock so two agents cannot reply to the same ticket at once
- Skills-based routing, agent availability and working hours
- Concurrency control on the ticket record

---

## Summary

Customer email arrives at one shared support mailbox, and tickets are assigned to a **team**
based on the customer's intent — never to an individual. Individual assignment and queue routing
are production scope, not built in the accelerator.

Today each developer runs a full local copy, so two people with the app open are two separate
systems racing for the same mailbox. Deploying to AWS gives one shared database and one inbound
path, which resolves that. Assigning work to a named person is separate work, listed in the
production scope document.
