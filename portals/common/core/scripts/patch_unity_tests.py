from pathlib import Path

test_path = Path(r"E:\maclient\Assets\Src\HotUpdate\Tests\PlayMode\ClientStartupHotUpdatePlayModeTests.cs")
text = test_path.read_text(encoding="utf-8")

text = text.replace(
    """            null,
            "active");""",
    """            null,
            "active",
            null);""",
    1,
)

needle = "        AddressableManager.SetPendingMetadataJson(resolved.MetadataJson, resolved.MetadataSourceLabel);\n        StartupHotUpdateBootstrapContext.Begin("
insert = """        AddressableManager.SetPendingMetadataJson(resolved.MetadataJson, resolved.MetadataSourceLabel);
        string bootstrapEnv = string.IsNullOrWhiteSpace(resolved.Environment) ? config.Environment : resolved.Environment;
        string bootstrapChannel = string.IsNullOrWhiteSpace(resolved.Channel) ? config.Channel : resolved.Channel;
        StartupHotUpdateBootstrapContext.Begin("""
if "bootstrapEnv" not in text:
    text = text.replace(needle, insert)
    text = text.replace(
        "            resolved.VersionCode,\n            resolved.Environment,\n            resolved.Channel,",
        "            resolved.VersionCode,\n            bootstrapEnv,\n            bootstrapChannel,",
        1,
    )

test_path.write_text(text, encoding="utf-8")
print("ok")
