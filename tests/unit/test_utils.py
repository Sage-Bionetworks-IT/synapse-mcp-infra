import json
import pytest
import tempfile
import yaml
from pathlib import Path

from src.utils import _deep_merge, load_context_config


class TestDeepMerge:
    """Test suite for the _deep_merge function."""

    def test_flat_merge(self):
        """Test merging flat dicts behaves like shallow merge."""
        base = {"a": 1, "b": 2}
        override = {"b": 3, "c": 4}
        assert _deep_merge(base, override) == {"a": 1, "b": 3, "c": 4}

    def test_nested_merge_preserves_base_keys(self):
        """Test that nested override only replaces specified keys."""
        base = {
            "MONITORING": {
                "notification_email": "",
                "alarms": {
                    "ecs_cpu_threshold": 80,
                    "ecs_memory_threshold": 80,
                },
            }
        }
        override = {
            "MONITORING": {
                "notification_email": "team@example.com",
            }
        }
        result = _deep_merge(base, override)
        assert result["MONITORING"]["notification_email"] == "team@example.com"
        assert result["MONITORING"]["alarms"]["ecs_cpu_threshold"] == 80
        assert result["MONITORING"]["alarms"]["ecs_memory_threshold"] == 80

    def test_nested_merge_overrides_specific_keys(self):
        """Test that specific nested keys can be overridden."""
        base = {"alarms": {"cpu": 80, "memory": 80}}
        override = {"alarms": {"cpu": 70}}
        result = _deep_merge(base, override)
        assert result == {"alarms": {"cpu": 70, "memory": 80}}

    def test_does_not_mutate_base(self):
        """Test that the base dict is not modified."""
        base = {"a": {"b": 1}}
        override = {"a": {"b": 2}}
        _deep_merge(base, override)
        assert base == {"a": {"b": 1}}

    def test_override_dict_with_non_dict(self):
        """Test that a non-dict value replaces a dict value."""
        base = {"a": {"b": 1}}
        override = {"a": "string"}
        assert _deep_merge(base, override) == {"a": "string"}


class TestLoadContextConfig:
    """Test suite for the load_context_config function."""

    @pytest.mark.parametrize(
        "invalid_env", ["invalid", "test", "production", "development", ""]
    )
    def test_invalid_environment_raises_value_error(self, invalid_env):
        """Test that invalid environment names raise ValueError."""
        with pytest.raises(ValueError, match=f"Invalid environment '{invalid_env}'"):
            load_context_config(invalid_env)

    @pytest.mark.parametrize("valid_env", ["dev", "stage", "prod"])
    def test_valid_environments(self, valid_env):
        """Test that valid environment names are accepted."""
        with tempfile.TemporaryDirectory() as temp_dir:
            config_file = Path(temp_dir) / f"{valid_env}.yaml"
            config_data = {
                "FQDN": f"{valid_env}.example.com",
                "VPC_CIDR": "10.0.0.0/16",
                "TAGS": {"Environment": valid_env},
            }

            with open(config_file, "w") as f:
                yaml.dump(config_data, f)

            result = load_context_config(valid_env, temp_dir)
            assert result["FQDN"] == f"{valid_env}.example.com"
            assert result["TAGS"]["Environment"] == valid_env

    def test_no_config_file_raises_file_not_found_error(self):
        """Test that missing config files raise FileNotFoundError."""
        with tempfile.TemporaryDirectory() as temp_dir:
            with pytest.raises(
                FileNotFoundError, match="No config file found for environment 'dev'"
            ):
                load_context_config("dev", temp_dir)

    @pytest.mark.parametrize(
        "file_extensions", [(".yaml", ".json"), (".yaml", ".yml"), (".yml", ".json")]
    )
    def test_multiple_config_files_raises_value_error(self, file_extensions):
        """Test that multiple config files for same environment raise ValueError."""
        with tempfile.TemporaryDirectory() as temp_dir:
            ext1, ext2 = file_extensions
            file1 = Path(temp_dir) / f"dev{ext1}"
            file2 = Path(temp_dir) / f"dev{ext2}"

            # Create content based on file extension
            if ext1 == ".json":
                with open(file1, "w") as f:
                    json.dump({"test": "file1"}, f)
            else:
                with open(file1, "w") as f:
                    yaml.dump({"test": "file1"}, f)

            if ext2 == ".json":
                with open(file2, "w") as f:
                    json.dump({"test": "file2"}, f)
            else:
                with open(file2, "w") as f:
                    yaml.dump({"test": "file2"}, f)

            with pytest.raises(
                ValueError, match="Multiple config files found for environment 'dev'"
            ):
                load_context_config("dev", temp_dir)

    @pytest.mark.parametrize(
        "file_extension,config_data",
        [
            (
                ".yaml",
                {
                    "VPC_CIDR": "10.0.0.0/16",
                    "FQDN": "example.com",
                    "TAGS": {"Environment": "dev"},
                },
            ),
            (".yml", {"VPC_CIDR": "10.0.0.0/16", "FQDN": "example.com"}),
            (
                ".json",
                {
                    "VPC_CIDR": "10.0.0.0/16",
                    "FQDN": "example.com",
                    "TAGS": {"Environment": "dev"},
                },
            ),
        ],
    )
    def test_load_config_files(self, file_extension, config_data):
        """Test loading configuration files in different formats."""
        with tempfile.TemporaryDirectory() as temp_dir:
            config_file = Path(temp_dir) / f"dev{file_extension}"

            if file_extension == ".json":
                with open(config_file, "w") as f:
                    json.dump(config_data, f)
            else:
                with open(config_file, "w") as f:
                    yaml.dump(config_data, f)

            result = load_context_config("dev", temp_dir)
            assert result == config_data

    def test_base_config_merging(self):
        """Test that base.yaml is properly merged with environment config."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create base config
            base_file = Path(temp_dir) / "base.yaml"
            base_config = {
                "VPC_CIDR": "10.0.0.0/16",
                "COMMON_SETTING": "base_value",
                "SHARED_SETTING": "from_base",
            }
            with open(base_file, "w") as f:
                yaml.dump(base_config, f)

            # Create environment config
            env_file = Path(temp_dir) / "dev.yaml"
            env_config = {
                "FQDN": "dev.example.com",
                "SHARED_SETTING": "from_env",  # This should override base
                "ENV_SPECIFIC": "dev_value",
            }
            with open(env_file, "w") as f:
                yaml.dump(env_config, f)

            result = load_context_config("dev", temp_dir)

            expected = {
                "VPC_CIDR": "10.0.0.0/16",  # from base
                "COMMON_SETTING": "base_value",  # from base
                "SHARED_SETTING": "from_env",  # env overrides base
                "FQDN": "dev.example.com",  # from env
                "ENV_SPECIFIC": "dev_value",  # from env
            }

            assert result == expected

    def test_base_config_deep_merging(self):
        """Test that nested dicts in base.yaml are deep-merged with env config."""
        with tempfile.TemporaryDirectory() as temp_dir:
            base_file = Path(temp_dir) / "base.yaml"
            base_config = {
                "MONITORING": {
                    "notification_email": "",
                    "alarms": {"ecs_cpu_threshold": 80, "ecs_memory_threshold": 80},
                }
            }
            with open(base_file, "w") as f:
                yaml.dump(base_config, f)

            env_file = Path(temp_dir) / "dev.yaml"
            env_config = {
                "FQDN": "dev.example.com",
                "MONITORING": {"notification_email": "team@example.com"},
            }
            with open(env_file, "w") as f:
                yaml.dump(env_config, f)

            result = load_context_config("dev", temp_dir)
            assert result["FQDN"] == "dev.example.com"
            assert result["MONITORING"]["notification_email"] == "team@example.com"
            assert result["MONITORING"]["alarms"]["ecs_cpu_threshold"] == 80

    def test_no_base_config(self):
        """Test loading config when base.yaml doesn't exist."""
        with tempfile.TemporaryDirectory() as temp_dir:
            env_file = Path(temp_dir) / "dev.yaml"
            env_config = {"FQDN": "dev.example.com"}

            with open(env_file, "w") as f:
                yaml.dump(env_config, f)

            result = load_context_config("dev", temp_dir)
            assert result == env_config

    def test_empty_base_config(self):
        """Test handling of empty base config file."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create empty base config
            base_file = Path(temp_dir) / "base.yaml"
            with open(base_file, "w") as f:
                f.write("")  # Empty file

            # Create environment config
            env_file = Path(temp_dir) / "dev.yaml"
            env_config = {"FQDN": "dev.example.com"}
            with open(env_file, "w") as f:
                yaml.dump(env_config, f)

            result = load_context_config("dev", temp_dir)
            assert result == env_config

    def test_empty_env_config(self):
        """Test handling of empty environment config file."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create base config
            base_file = Path(temp_dir) / "base.yaml"
            base_config = {"VPC_CIDR": "10.0.0.0/16"}
            with open(base_file, "w") as f:
                yaml.dump(base_config, f)

            # Create empty environment config
            env_file = Path(temp_dir) / "dev.yaml"
            with open(env_file, "w") as f:
                f.write("")  # Empty file

            result = load_context_config("dev", temp_dir)
            assert result == base_config

    def test_custom_config_dir(self):
        """Test using a custom config directory."""
        with tempfile.TemporaryDirectory() as temp_dir:
            custom_dir = Path(temp_dir) / "custom_config"
            custom_dir.mkdir()

            config_file = custom_dir / "dev.yaml"
            config_data = {"FQDN": "custom.example.com"}

            with open(config_file, "w") as f:
                yaml.dump(config_data, f)

            result = load_context_config("dev", str(custom_dir))
            assert result == config_data

    @pytest.mark.parametrize(
        "file_extension,invalid_content,expected_exception",
        [
            (".yaml", "invalid: yaml: content: [unclosed", yaml.YAMLError),
            (".yml", "invalid: yaml: content: [unclosed", yaml.YAMLError),
            (".json", '{"invalid": json content}', json.JSONDecodeError),
        ],
    )
    def test_invalid_config_content(
        self, file_extension, invalid_content, expected_exception
    ):
        """Test handling of invalid configuration file content."""
        with tempfile.TemporaryDirectory() as temp_dir:
            config_file = Path(temp_dir) / f"dev{file_extension}"
            with open(config_file, "w") as f:
                f.write(invalid_content)

            with pytest.raises(expected_exception):
                load_context_config("dev", temp_dir)
