---
id: TASK-2
title: 'Phase 2: Инкрементальный парсер'
status: In Progress
labels:
- phase:2
- migrated
dependencies:
- TASK-1
references:
- examples\roadmap\roadmap.md
created_date: 2026-11-11 16:02
updated_date: 2026-11-11 16:02
---

## Description

Импортировано из roadmap.md.

Шаги:
1. Разбирать сообщения по мере поступления
2. Сохранять недособранный хвост буфера
3. Замерять бюджет на сообщение** — в работе

## Acceptance Criteria

- [ ] #1 Разбор не строит полное дерево документа.
- [ ] #2 Хвост буфера переносится между вызовами.
- [ ] #3 Бюджет укладывается в 40 мс на сообщение.
