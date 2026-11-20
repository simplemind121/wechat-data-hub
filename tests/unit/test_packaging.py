import io
import json
import tarfile

from scripts.package_delivery import merge_docker_archives


def saved_image(tag, config):
    stream = io.BytesIO()
    entries = {
        config: b"synthetic-config",
        "shared/layer.tar": b"synthetic-layer",
        "index.json": b"old-index",
        "oci-layout": b"old-layout",
        "manifest.json": json.dumps(
            [{"Config": config, "RepoTags": [tag], "Layers": ["shared/layer.tar"]}]
        ).encode(),
    }
    with tarfile.open(fileobj=stream, mode="w") as archive:
        for name, data in entries.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))
    return stream.getvalue()


def test_combined_image_archive_preserves_all_tags_and_reference_bytes():
    output = io.BytesIO()
    merge_docker_archives(
        [saved_image("synthetic-api:1", "a.json"), saved_image("synthetic-web:1", "b.json")], output
    )
    with tarfile.open(fileobj=io.BytesIO(output.getvalue())) as archive:
        manifest = json.load(archive.extractfile("manifest.json"))
        assert {tag for item in manifest for tag in item["RepoTags"]} == {
            "synthetic-api:1",
            "synthetic-web:1",
        }
        assert archive.getnames().count("shared/layer.tar") == 1
        for item in manifest:
            assert archive.extractfile(item["Config"]).read() == b"synthetic-config"
            assert archive.extractfile(item["Layers"][0]).read() == b"synthetic-layer"
        assert "index.json" not in archive.getnames()
