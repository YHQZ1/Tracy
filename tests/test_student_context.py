from tracy.application.setup_student_context import collect_student_context
from tracy.domain.entities import Course
from tracy.domain.student import LabBatch, StudentContext
from tracy.persistence.student_context_store import JsonStudentContextStore


def test_student_context_normalizes_and_round_trips(tmp_path) -> None:
    context = StudentContext(
        name="  Uttkarsh   Ruparel ",
        college_email="UTTKARSH@COLLEGE.EDU ",
        prn="  23070122227 ",
        program=" Computer Science and Engineering ",
        division=" a ",
        year=4,
        semester=7,
        lab_batches=(LabBatch(course_id="devops", course_name=" DevOps Lab ", batch=" lab 1 "),),
    )

    assert context.name == "Uttkarsh Ruparel"
    assert context.college_email == "uttkarsh@college.edu"
    assert context.prn == "23070122227"
    assert context.program == "Computer Science and Engineering"
    assert context.division == "A"
    assert context.lab_batches[0].batch == "LAB 1"

    store = JsonStudentContextStore(tmp_path)
    store.save(context)

    assert store.load() == context


def test_collect_student_context_asks_for_detected_lab_batches() -> None:
    answers = iter(
        [
            "Uttkarsh Ruparel",
            "uttkarsh@college.edu",
            "23070122227",
            "Computer Science and Engineering",
            "A",
            "4",
            "7",
            "Lab 1",
            "A2",
        ]
    )
    prompts: list[str] = []

    def ask(prompt: str, default: str | None = None) -> str:
        prompts.append(prompt)
        return next(answers)

    context = collect_student_context(
        (
            Course(id="theory", name="Compiler Construction"),
            Course(id="devops", name="DevOps Lab"),
            Course(id="compiler-lab", name="Compiler Construction Lab"),
        ),
        ask,
    )

    assert len(prompts) == 9
    assert [(item.course_id, item.batch) for item in context.lab_batches] == [
        ("devops", "LAB 1"),
        ("compiler-lab", "A2"),
    ]
