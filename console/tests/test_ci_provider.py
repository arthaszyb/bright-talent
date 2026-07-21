from console.providers import MockCIProvider


def test_instance_ci_available_when_makefile_present(tmp_path):
    (tmp_path / "Makefile").write_text("build:\n\techo hi\n")
    status = MockCIProvider().instance_ci(tmp_path)
    assert status["available"] is True
    assert status["status"] == "passing"
    assert all(s["status"] == "pass" for s in status["steps"])
    assert len(status["steps"]) > 0


def test_instance_ci_unavailable_without_makefile(tmp_path):
    status = MockCIProvider().instance_ci(tmp_path)
    assert status["available"] is False
    assert status["steps"] == []


def test_skills_ci_available_when_workflow_present(tmp_path):
    wf = tmp_path / ".github" / "workflows"
    wf.mkdir(parents=True)
    (wf / "skills-ci.yml").write_text("name: ci\n")
    status = MockCIProvider().skills_ci(tmp_path)
    assert status["available"] is True


def test_skills_ci_available_from_repo_root_workflow(tmp_path):
    wf = tmp_path / ".github" / "workflows"
    wf.mkdir(parents=True)
    (wf / "skills-ci.yml").write_text("name: ci\n")
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    status = MockCIProvider().skills_ci(skills_dir)
    assert status["available"] is True


def test_skills_ci_unavailable_without_workflow(tmp_path):
    status = MockCIProvider().skills_ci(tmp_path)
    assert status["available"] is False
