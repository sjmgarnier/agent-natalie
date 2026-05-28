---
cssclasses:
  - wide-page
  - natalie-dashboard
tags:
  - natalie-skip
obsidianUIMode: preview
---

> [!banner] `= dateformat(date(today), "cccc, MMMM d, yyyy")`
> 
> `$= dv.pages().length + " notes · " + dv.pages().where(p => p.file.mtime >= dv.date("today")).length + " modified today"`

---

> [!multi-column]
>
>> [!abstract]+ Daily Plan
>> ![[Natalie/Today]]
>
>> [!task-list]+ Open Tasks
>> ```dataview
>> TASK
>> WHERE !completed
>> SORT due ASC
>> LIMIT 15
>> ```

---

> [!multi-column]
>
>> [!example]+ Recently Modified
>> ```dataview
>> TABLE WITHOUT ID link(file.path, file.name) AS File, dateformat(file.mtime, "MMM d HH:mm") AS Modified
>> WHERE file.path != this.file.path AND !contains(file.tags, "natalie-skip")
>> SORT file.mtime DESC
>> LIMIT 8
>> ```
>
>> [!briefing]+ Briefing
>> ![[Natalie/Briefing]]
>
>> [!links]+ Links
>> ![[Natalie/Links]]

---
