"""Ranh giới giữa các service (repo-and-testing.md §1, bất biến #2)."""
import ast
import pathlib
import tomllib

ROOT = pathlib.Path(__file__).resolve().parents[2]
SERVICES = {"core": "core", "agent-runtime": "agent_runtime", "payment-gate": "gate", "sim-world": "sim_world"}
DB_DRIVERS = {"psycopg", "psycopg2", "asyncpg", "sqlalchemy"}


def imported_roots(src: pathlib.Path) -> set[str]:
    roots = set()
    for f in src.rglob("*.py"):
        for node in ast.walk(ast.parse(f.read_text(), str(f))):
            if isinstance(node, ast.Import):
                roots |= {a.name.split(".")[0] for a in node.names}
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                roots.add(node.module.split(".")[0])
    return roots


def test_services_do_not_import_each_other():
    for svc, pkg in SERVICES.items():
        others = set(SERVICES.values()) - {pkg}
        leaked = imported_roots(ROOT / "services" / svc / "src") & others
        assert not leaked, f"{svc} import service khác: {leaked}"


def test_agent_runtime_has_no_db_driver():
    src = ROOT / "services" / "agent-runtime"
    assert not imported_roots(src / "src") & DB_DRIVERS
    deps = tomllib.loads((src / "pyproject.toml").read_text())["project"]["dependencies"]
    assert not {d.split("[")[0].split(">")[0].split("=")[0].strip().lower() for d in deps} & DB_DRIVERS
