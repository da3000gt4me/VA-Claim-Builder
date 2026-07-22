from core.drafting.packet_generator import PacketGenerator

def test_packet_generation(tmp_path):
    path, manifest = PacketGenerator(tmp_path).generate_review_packet("Migraines", "doctor_nexus", "Draft text", [], [], ["Clarify onset"])
    assert path.exists()
    assert path.with_suffix(".manifest.json").exists()
    assert manifest["unresolved_question_count"] == 1
