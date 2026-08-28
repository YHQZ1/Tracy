# Tracy data model

The first canonical records are:

- `Institution` — the Moodle site being connected.
- `User` — the authenticated student within that institution.
- `Course` — a course visible to the student.
- `Enrollment` — the relationship between a user and course.
- `Activity` — an assignment, quiz, lab, forum, or other Moodle activity.
- `Assignment` — an activity with submission and due-date semantics.
- `Grade` — a user-specific grade or course result.
- `AttendanceRecord` — a user-specific attendance observation.
- `Announcement` — a forum or announcement item.
- `Document` — an attached file and its Moodle source metadata.
- `DocumentChunk` — extracted text with document and page provenance.
- `Reminder` — a confirmed event scheduled for a user and notification channel.
- `SyncRun` — an idempotent synchronization attempt and its checkpoint.

All user-specific data must be scoped by both `institution_id` and `user_id`,
even during the single-institution pilot.
