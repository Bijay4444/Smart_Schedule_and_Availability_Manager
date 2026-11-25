import pytest

from scripts.sync_vm_environment import KEYS, quote_value, remote_program, update_text


def test_update_preserves_database_and_django_settings_and_quotes_dollars():
    old = 'APP_IMAGE=smart-schedule:original\nDJANGO_SECRET_KEY=keep\nPOSTGRES_PASSWORD=keep-too\nGROQ_API_KEY=old\n'
    new = update_text(old, {'GROQ_API_KEY': 'value$literal', 'GOOGLE_CLIENT_ID': 'id'})
    assert new.startswith('APP_IMAGE=smart-schedule:original\nDJANGO_SECRET_KEY=keep\nPOSTGRES_PASSWORD=keep-too\n')
    assert "GROQ_API_KEY='value$literal'\n" in new
    assert "GOOGLE_CLIENT_ID='id'\n" in new
    assert new.count('GROQ_API_KEY=') == 1
    assert update_text(new, {'GROQ_API_KEY': 'value$literal', 'GOOGLE_CLIENT_ID': 'id'}) == new


@pytest.mark.parametrize('values', [
    {'POSTGRES_PASSWORD': 'wrong'}, {'GROQ_API_KEY': 'line\nbreak'},
    {'GROQ_API_KEY': "quote'"}, {'GROQ_API_KEY': 'back\\slash'},
])
def test_unsafe_or_unrelated_values_are_rejected(values):
    with pytest.raises(ValueError):
        update_text('APP_IMAGE=keep\n', values)


def test_duplicate_environment_entries_are_rejected():
    with pytest.raises(ValueError, match='Duplicate'):
        update_text('GROQ_API_KEY=a\nGROQ_API_KEY=b\n', {'GROQ_API_KEY': 'new'})


def test_remote_updater_compiles_and_uses_same_allowlist():
    compile(remote_program(), '<remote updater>', 'exec')
    assert 'POSTGRES_PASSWORD' not in KEYS


@pytest.mark.parametrize('filename', ['compose.vm.yaml', 'compose.yaml'])
def test_compose_forwards_all_integration_settings(filename):
    from pathlib import Path
    contents = Path(filename).read_text()
    for key in KEYS:
        assert f'{key}: ${{{key}:-' in contents


def test_remote_program_updates_privately_and_creates_backup(tmp_path, monkeypatch, capsys):
    from io import StringIO
    import json
    import stat
    import sys
    target = tmp_path / '.env'
    original = 'APP_IMAGE=keep-image\nDJANGO_SECRET_KEY=keep-secret\nPOSTGRES_PASSWORD=keep-password\n'
    target.write_text(original)
    target.chmod(0o600)
    monkeypatch.setattr(sys, 'stdin', StringIO(json.dumps({'apply': True, 'values': {'GROQ_API_KEY': 'private-value$literal'}})))
    # Use the actual remote program against an isolated temporary environment file.
    program = remote_program().replace("Path('/opt/smart-schedule/.env')", f'Path({str(target)!r})')
    exec(compile(program, '<remote updater>', 'exec'), {})
    output = capsys.readouterr().out
    assert 'private-value' not in output
    assert 'keep-secret' not in output
    assert json.loads(output)['configured']['GROQ_API_KEY'] is True
    assert target.read_text().startswith(original)
    assert "GROQ_API_KEY='private-value$literal'" in target.read_text()
    assert stat.S_IMODE(target.stat().st_mode) == 0o600
    backup, = tmp_path.glob('integration-env-*.bak')
    assert backup.read_text() == original
    assert stat.S_IMODE(backup.stat().st_mode) == 0o600
