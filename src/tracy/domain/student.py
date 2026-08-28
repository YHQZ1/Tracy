from dataclasses import dataclass


def _normalized_text(value: str) -> str:
    return " ".join(value.split())


@dataclass(frozen=True, slots=True)
class LabBatch:
    """A student-specific batch assignment for one Moodle lab course."""

    course_id: str
    course_name: str
    batch: str

    def __post_init__(self) -> None:
        course_id = self.course_id.strip()
        course_name = _normalized_text(self.course_name)
        batch = _normalized_text(self.batch).upper()
        if not course_id or not course_name or not batch:
            raise ValueError("Lab batch entries require a course and batch.")
        object.__setattr__(self, "course_id", course_id)
        object.__setattr__(self, "course_name", course_name)
        object.__setattr__(self, "batch", batch)


@dataclass(frozen=True, slots=True)
class StudentContext:
    """Locally stored identity and academic context for one Tracy user."""

    name: str
    college_email: str
    prn: str
    program: str
    division: str
    year: int
    semester: int
    lab_batches: tuple[LabBatch, ...] = ()

    def __post_init__(self) -> None:
        name = _normalized_text(self.name)
        college_email = self.college_email.strip().casefold()
        prn = self.prn.strip().upper()
        program = _normalized_text(self.program)
        division = _normalized_text(self.division).upper()
        if not name or not college_email or "@" not in college_email:
            raise ValueError("A valid name and college email are required.")
        if not prn or not program or not division:
            raise ValueError("PRN, program, and division are required.")
        if self.year not in {1, 2, 3, 4}:
            raise ValueError("Year must be between 1 and 4.")
        if self.semester not in set(range(1, 9)):
            raise ValueError("Semester must be between 1 and 8.")
        course_ids = [item.course_id for item in self.lab_batches]
        if len(course_ids) != len(set(course_ids)):
            raise ValueError("Each lab course may have only one configured batch.")
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "college_email", college_email)
        object.__setattr__(self, "prn", prn)
        object.__setattr__(self, "program", program)
        object.__setattr__(self, "division", division)
        object.__setattr__(self, "lab_batches", tuple(self.lab_batches))
