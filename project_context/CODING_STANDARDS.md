# Coding Standards

## Architecture Rules

- Modular structure only
- No monolithic AI logic files
- Separate memory, retrieval, and reasoning layers

---

## Backend Rules

- API-first design
- Stateless endpoints where possible
- Clear separation between AI and system logic

---

## Naming Conventions

- camelCase for JS/TS
- snake_case for Python
- descriptive module names only

---

## AI Integration Rules

- All LLM calls must go through a single abstraction layer
- No direct API calls inside business logic
- All prompts must be version-controlled