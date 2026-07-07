from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[2]


def test_setup_postgres_unquoted_sql_blocks_do_not_run_shell_substitutions():
    script = (ROOT / "scripts" / "setup_postgres.sh").read_text()

    sql_blocks = re.findall(r"<<SQL\n(.*?)\nSQL", script, flags=re.S)

    assert sql_blocks
    for block in sql_blocks:
        assert "`" not in block
        assert "$(" not in block
