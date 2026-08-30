function run(argv) {
  const input = JSON.parse(argv[0]);
  const reminders = Application("Reminders");
  let targetList;

  if (input.list) {
    const wanted = input.list.toLocaleLowerCase();
    const matches = reminders.lists().filter(
      (list) => list.name().toLocaleLowerCase() === wanted,
    );
    if (matches.length === 0) {
      throw new Error("No Reminders list named “" + input.list + "” exists.");
    }
    if (matches.length > 1) {
      throw new Error("More than one Reminders list is named “" + input.list + "”.");
    }
    targetList = matches[0];
  } else {
    targetList = reminders.defaultList();
  }

  const properties = {
    name: input.title,
    priority: input.priority,
  };
  if (input.notes) properties.body = input.notes;
  if (input.due_kind === "all_day") {
    properties.alldayDueDate = new Date(input.due + "T12:00:00");
  } else if (input.due_kind === "timed") {
    properties.dueDate = new Date(input.due);
  }

  const reminder = reminders.Reminder(properties);
  targetList.reminders.push(reminder);
  return JSON.stringify({
    id: reminder.id(),
    title: reminder.name(),
    list: targetList.name(),
    due: input.due,
    priority: input.priority_label,
  });
}
