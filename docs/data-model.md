# Tracy data model

The first canonical records are:

- `Institution` — the Moodle site being connected.
- `User` — the authenticated student within that institution.
- `StudentContext` — local PRN, program, division, year, semester, and lab-batch preferences.
- `LabBatch` — the selected batch for one lab course, such as `LAB 1` or `A2`.
- `Course` — a course visible to the student.
- `Enrollment` — the relationship between a user and course.
- `Activity` — an assignment, quiz, lab, forum, or other Moodle activity.
- `Assignment` — an activity with submission and due-date semantics.
- `Grade` — a user-specific grade or course result.
- `AttendanceRecord` — a user-specific attendance observation.
- `AttendanceSummary` — a user-specific per-course total, marked, attended, and percentage summary.
- `Announcement` — a forum or announcement item.
- `Document` — an attached file and its Moodle source metadata.
- `DocumentChunk` — extracted text with document and page provenance.
- `Reminder` — a confirmed event scheduled for a user and notification channel.
- `SyncRun` — an idempotent synchronization attempt and its checkpoint.

All user-specific data must be scoped by both `institution_id` and `user_id`,
even during the single-institution pilot.
