function text(value) {
  return value === null || value === undefined ? "" : String(value);
}

function localDate(value) {
  const date = new Date(value);
  const year = String(date.getFullYear()).padStart(4, "0");
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function priorityLabel(value) {
  if (value >= 1 && value <= 4) return "high";
  if (value === 5) return "medium";
  if (value >= 6 && value <= 9) return "low";
  return "none";
}

function exactList(reminders, name) {
  const wanted = name.toLocaleLowerCase();
  const matches = reminders.lists().filter(
    (list) => list.name().toLocaleLowerCase() === wanted,
  );
  if (matches.length === 0) {
    throw new Error(`No Reminders list named “${name}” exists.`);
  }
  if (matches.length > 1) {
    throw new Error(`More than one Reminders list is named “${name}”.`);
  }
  return matches[0];
}

function exactListId(reminders, id) {
  const matches = reminders.lists().filter((list) => list.id() === id);
  if (matches.length === 0) {
    throw new Error(`No Reminders list with ID “${id}” exists.`);
  }
  return matches[0];
}

function selectedList(reminders, input) {
  if (input.list_id) return exactListId(reminders, input.list_id);
  if (input.list) return exactList(reminders, input.list);
  return reminders.defaultList();
}

function ensureAvailableListName(reminders, name, currentId) {
  const wanted = name.toLocaleLowerCase();
  const duplicate = reminders.lists().find(
    (list) => list.name().toLocaleLowerCase() === wanted && list.id() !== currentId,
  );
  if (duplicate) {
    throw new Error(`A Reminders list named “${name}” already exists.`);
  }
}

function findReminder(reminders, id) {
  const reminder = reminders.reminders.byId(id);
  try {
    if (reminder.id() === id) return { reminder, list: reminder.container() };
  } catch (error) {}
  throw new Error(`No reminder with ID “${id}” exists.`);
}

function reminderDue(reminder) {
  const timed = reminder.dueDate();
  const allDay = reminder.alldayDueDate();
  if (timed && allDay && new Date(timed).getTime() !== new Date(allDay).getTime()) {
    return { due: new Date(timed).toISOString(), due_kind: "timed" };
  }
  if (allDay) return { due: localDate(allDay), due_kind: "all_day" };
  if (timed) return { due: new Date(timed).toISOString(), due_kind: "timed" };
  return { due: null, due_kind: null };
}

function serializeReminder(reminder, list) {
  const due = reminderDue(reminder);
  const completionDate = reminder.completionDate();
  const remindAt = reminder.remindMeDate();
  const creationDate = reminder.creationDate();
  const modificationDate = reminder.modificationDate();
  return {
    id: reminder.id(),
    title: text(reminder.name()),
    list: list.name(),
    list_id: list.id(),
    notes: text(reminder.body()),
    due: due.due,
    due_kind: due.due_kind,
    completed: Boolean(reminder.completed()),
    completion_date: completionDate
      ? new Date(completionDate).toISOString()
      : null,
    priority: priorityLabel(reminder.priority()),
    flagged: Boolean(reminder.flagged()),
    remind_at: remindAt ? new Date(remindAt).toISOString() : null,
    creation_date: creationDate ? new Date(creationDate).toISOString() : null,
    modification_date: modificationDate
      ? new Date(modificationDate).toISOString()
      : null,
  };
}

function serializeList(reminders, list) {
  return {
    id: list.id(),
    name: list.name(),
    reminder_count: list.reminders().length,
    default: list.id() === reminders.defaultList().id(),
  };
}

function addReminder(reminders, input) {
  const targetList = selectedList(reminders, input);
  const properties = {
    name: input.title,
    priority: input.priority,
    flagged: input.flagged,
  };
  if (input.notes) properties.body = input.notes;
  if (input.due_kind === "all_day") {
    properties.alldayDueDate = new Date(`${input.due}T12:00:00`);
  } else if (input.due_kind === "timed") {
    properties.dueDate = new Date(input.due);
  }
  const reminder = reminders.Reminder(properties);
  targetList.reminders.push(reminder);
  return { reminder: serializeReminder(reminder, targetList) };
}

function listReminderLists(reminders) {
  return {
    lists: reminders.lists().map((list) => serializeList(reminders, list)),
  };
}

function createReminderList(reminders, input) {
  ensureAvailableListName(reminders, input.name, null);
  const list = reminders.List({ name: input.name });
  reminders.defaultAccount().lists.push(list);
  return { list: serializeList(reminders, list) };
}

function renameReminderList(reminders, input) {
  const list = exactListId(reminders, input.id);
  ensureAvailableListName(reminders, input.name, list.id());
  list.name = input.name;
  return { list: serializeList(reminders, list) };
}

function reminderLocalDueDate(reminder) {
  const allDay = reminder.alldayDueDate();
  if (allDay) return localDate(allDay);
  const timed = reminder.dueDate();
  return timed ? localDate(timed) : null;
}

function searchReminders(reminders, input) {
  const lists = input.list || input.list_id
    ? [selectedList(reminders, input)]
    : reminders.lists();
  const query = input.query ? input.query.toLocaleLowerCase() : null;
  const found = [];
  let matched = 0;
  let truncated = false;

  outer: for (const list of lists) {
    for (const reminder of list.reminders()) {
      const completed = Boolean(reminder.completed());
      if (input.completed === "open" && completed) continue;
      if (input.completed === "completed" && !completed) continue;
      if (Object.prototype.hasOwnProperty.call(input, "flagged")) {
        if (Boolean(reminder.flagged()) !== input.flagged) continue;
      }
      if (query) {
        const haystack = `${text(reminder.name())}\n${text(reminder.body())}`
          .toLocaleLowerCase();
        if (!haystack.includes(query)) continue;
      }
      if (input.due_start || input.due_end) {
        const dueDate = reminderLocalDueDate(reminder);
        if (!dueDate) continue;
        if (input.due_start && dueDate < input.due_start) continue;
        if (input.due_end && dueDate > input.due_end) continue;
      }
      if (matched < input.offset) {
        matched += 1;
        continue;
      }
      if (found.length === input.limit) {
        truncated = true;
        break outer;
      }
      found.push(serializeReminder(reminder, list));
      matched += 1;
    }
  }
  return {
    reminders: found,
    count: found.length,
    truncated,
    next_offset: truncated ? input.offset + found.length : null,
  };
}

function updateReminder(reminders, input) {
  let record = findReminder(reminders, input.id);
  let reminder = record.reminder;
  if (Object.prototype.hasOwnProperty.call(input, "title")) {
    reminder.name = input.title;
  }
  if (Object.prototype.hasOwnProperty.call(input, "notes")) {
    reminder.body = input.notes;
  }
  if (Object.prototype.hasOwnProperty.call(input, "priority")) {
    reminder.priority = input.priority;
  }
  if (Object.prototype.hasOwnProperty.call(input, "flagged")) {
    reminder.flagged = input.flagged;
  }
  if (Object.prototype.hasOwnProperty.call(input, "due")) {
    const currentKind = reminderDue(reminder).due_kind;
    if (currentKind && currentKind !== input.due_kind) {
      throw new Error(
        `Cannot switch this reminder from ${currentKind} to ${input.due_kind}; create a replacement or change it in Reminders.`,
      );
    }
    if (input.due_kind === "all_day") {
      reminder.alldayDueDate = new Date(`${input.due}T12:00:00`);
    } else {
      reminder.dueDate = new Date(input.due);
    }
  }
  if (
    Object.prototype.hasOwnProperty.call(input, "list") ||
    Object.prototype.hasOwnProperty.call(input, "list_id")
  ) {
    const targetList = selectedList(reminders, input);
    if (targetList.id() !== record.list.id()) {
      reminders.move(reminder, { to: targetList });
      record = findReminder(reminders, input.id);
      reminder = record.reminder;
    }
  }
  return { reminder: serializeReminder(reminder, record.list) };
}

function run(argv) {
  const input = JSON.parse(argv[0]);
  const reminders = Application("Reminders");

  switch (input.action) {
    case "list_reminder_lists":
      return JSON.stringify(listReminderLists(reminders));
    case "create_reminder_list":
      return JSON.stringify(createReminderList(reminders, input));
    case "rename_reminder_list":
      return JSON.stringify(renameReminderList(reminders, input));
    case "search_reminders":
      return JSON.stringify(searchReminders(reminders, input));
    case "get_reminder": {
      const record = findReminder(reminders, input.id);
      return JSON.stringify({
        reminder: serializeReminder(record.reminder, record.list),
      });
    }
    case "add_reminder":
      return JSON.stringify(addReminder(reminders, input));
    case "update_reminder":
      return JSON.stringify(updateReminder(reminders, input));
    case "set_reminder_completed": {
      const record = findReminder(reminders, input.id);
      record.reminder.completed = input.completed;
      return JSON.stringify({
        reminder: serializeReminder(record.reminder, record.list),
      });
    }
    case "delete_reminder": {
      const record = findReminder(reminders, input.id);
      const deleted = serializeReminder(record.reminder, record.list);
      reminders.delete(record.reminder);
      return JSON.stringify({ deleted });
    }
    default:
      throw new Error("Unsupported reminder action.");
  }
}
