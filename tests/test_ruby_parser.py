"""Ruby parser tests.

Tests for Ruby language support including basic syntax and Rails DSL patterns.
"""

import pytest
from pathlib import Path
from chunkhound.core.types.common import FileId, Language
from chunkhound.parsers.parser_factory import get_parser_factory


@pytest.fixture
def parser_factory():
    """Get parser factory instance."""
    return get_parser_factory()


@pytest.fixture
def basic_ruby_file():
    """Load basic Ruby fixture."""
    fixture_path = Path(__file__).parent / "fixtures" / "ruby" / "basic.rb"
    return fixture_path.read_text()


@pytest.fixture
def rails_model_file():
    """Load Rails model fixture."""
    fixture_path = Path(__file__).parent / "fixtures" / "ruby" / "rails_model.rb"
    return fixture_path.read_text()


class TestRubyBasics:
    """Test basic Ruby syntax parsing."""

    def test_class_parsing(self, parser_factory, basic_ruby_file):
        """Test that Ruby classes are parsed correctly."""
        parser = parser_factory.create_parser(Language.RUBY)

        chunks = parser.parse_content(basic_ruby_file, "test.rb", FileId(1))

        assert chunks is not None
        assert len(chunks) > 0

        # Find class chunks
        classes = [c for c in chunks if c.metadata.get("kind") == "class"]
        assert len(classes) >= 2  # User and AdminUser

        class_names = {c.symbol for c in classes}
        assert "User" in class_names
        assert "AdminUser" in class_names

    def test_module_parsing(self, parser_factory, basic_ruby_file):
        """Test that Ruby modules are parsed correctly."""
        parser = parser_factory.create_parser(Language.RUBY)

        chunks = parser.parse_content(basic_ruby_file, "test.rb", FileId(1))

        assert chunks is not None

        # Find module chunks
        modules = [c for c in chunks if c.metadata.get("kind") == "module"]
        assert len(modules) >= 1
        assert modules[0].symbol == "Utils"

    def test_method_parsing(self, parser_factory, basic_ruby_file):
        """Test that Ruby methods are parsed correctly."""
        parser = parser_factory.create_parser(Language.RUBY)

        chunks = parser.parse_content(basic_ruby_file, "test.rb", FileId(1))

        assert chunks is not None

        # Find method chunks
        methods = [c for c in chunks if c.metadata.get("kind") == "method"]
        assert len(methods) > 0

        method_names = {c.symbol for c in methods}
        assert "greet" in method_names or "initialize" in method_names

    def test_singleton_method_parsing(self, parser_factory):
        """Test that Ruby class methods are parsed correctly."""
        code = """
class User
  def self.create(name)
    new(name)
  end
end
"""
        parser = parser_factory.create_parser(Language.RUBY)

        chunks = parser.parse_content(code, "test.rb", FileId(1))

        assert chunks is not None

        # Find class method
        methods = [c for c in chunks if c.metadata.get("kind") == "method"]
        class_methods = [m for m in methods if m.metadata.get("is_class_method")]
        assert len(class_methods) >= 1

    def test_constant_extraction(self, parser_factory, basic_ruby_file):
        """Test that Ruby constants are extracted."""
        parser = parser_factory.create_parser(Language.RUBY)

        chunks = parser.parse_content(basic_ruby_file, "test.rb", FileId(1))

        assert chunks is not None

        # Find constant chunks
        constants = [c for c in chunks if c.metadata.get("kind") == "constant"]
        assert len(constants) >= 1

        # Check for MAX_RETRIES constant
        constant_names = {c.symbol for c in constants}
        assert "MAX_RETRIES" in constant_names

    def test_comment_extraction(self, parser_factory, basic_ruby_file):
        """Test that Ruby comments are extracted."""
        parser = parser_factory.create_parser(Language.RUBY)

        chunks = parser.parse_content(basic_ruby_file, "test.rb", FileId(1))

        assert chunks is not None

        # Find comment chunks
        comments = [c for c in chunks if "comment" in c.chunk_type.value.lower()]
        assert len(comments) > 0

    def test_shebang_detection(self, parser_factory):
        """Test that shebang comments are properly detected as shebang type."""
        code = """#!/usr/bin/env ruby

class Foo
  def bar
  end
end
"""
        parser = parser_factory.create_parser(Language.RUBY)

        chunks = parser.parse_content(code, "test.rb", FileId(1))

        assert chunks is not None

        # Find comment chunks
        comments = [c for c in chunks if "comment" in c.chunk_type.value.lower()]
        assert len(comments) >= 1

        # Check for shebang comment type - this is the fix we made
        shebang_comments = [c for c in comments if c.metadata.get("comment_type") == "shebang"]
        assert len(shebang_comments) == 1
        assert shebang_comments[0].metadata.get("is_doc_comment") is True

    def test_superclass_detection(self, parser_factory, basic_ruby_file):
        """Test that superclass is detected in class definitions."""
        parser = parser_factory.create_parser(Language.RUBY)

        chunks = parser.parse_content(basic_ruby_file, "test.rb", FileId(1))

        assert chunks is not None

        # Find AdminUser class
        admin_class = [c for c in chunks if c.symbol == "AdminUser"]
        assert len(admin_class) == 1
        assert admin_class[0].metadata.get("superclass") == "User"

    def test_all_methods_parsed(self, parser_factory, basic_ruby_file):
        """Test that ALL methods are parsed, including private methods and methods after other methods."""
        parser = parser_factory.create_parser(Language.RUBY)

        chunks = parser.parse_content(basic_ruby_file, "test.rb", FileId(1))

        assert chunks is not None

        # Find all method chunks
        methods = [c for c in chunks if c.metadata.get("kind") == "method"]
        method_map = {c.symbol: (c.start_line, c.end_line) for c in methods}

        # Verify we have all 8 expected methods (including duplicates like initialize)
        assert len(methods) == 8, f"Expected 8 methods, found {len(methods)}"

        # Verify specific methods that were previously missing or had wrong ranges
        # These tests ensure the sibling merge fix is working
        assert "format_string" in method_map
        assert "process" in method_map, "process method in Utils module should be found"
        assert "normalize_email" in method_map, "normalize_email private method should be found"
        assert "admin?" in method_map, "admin? method in AdminUser should be found"

        # Verify line ranges are correct (not extended beyond actual method)
        # create should end at line 37, not absorb normalize_email at line 41
        create_methods = [c for c in methods if c.symbol == "create"]
        assert len(create_methods) == 1
        assert create_methods[0].end_line <= 37, "create method should not extend beyond line 37"

        # AdminUser's initialize should end around line 51, not absorb admin? at line 53
        admin_inits = [c for c in methods if c.symbol == "initialize" and c.start_line > 45]
        assert len(admin_inits) == 1
        assert admin_inits[0].end_line <= 51, "AdminUser initialize should not extend beyond line 51"


class TestImportResolution:
    """Test Ruby import/require resolution."""

    def test_require_detection(self, parser_factory):
        """Test that require statements are detected."""
        code = """
require 'json'
require 'active_record'
"""
        parser = parser_factory.create_parser(Language.RUBY)

        chunks = parser.parse_content(code, "test.rb", FileId(1))

        assert chunks is not None

        # Find import chunks
        imports = [c for c in chunks if c.metadata.get("import_type") == "require"]
        assert len(imports) >= 1

    def test_require_relative_detection(self, parser_factory):
        """Test that require_relative statements are detected."""
        code = """
require_relative 'helper'
require_relative '../lib/utils'
"""
        parser = parser_factory.create_parser(Language.RUBY)

        chunks = parser.parse_content(code, "test.rb", FileId(1))

        assert chunks is not None

        # Find import chunks
        imports = [c for c in chunks if c.metadata.get("import_type") == "require_relative"]
        assert len(imports) >= 1


class TestRailsPatterns:
    """Test Rails DSL pattern detection (Phase 2)."""

    def test_rails_model_parsing(self, parser_factory, rails_model_file):
        """Test that Rails models parse successfully."""
        parser = parser_factory.create_parser(Language.RUBY)

        chunks = parser.parse_content(rails_model_file, "post.rb", FileId(1))

        assert chunks is not None
        assert len(chunks) > 0

        # Find the Post class
        classes = [c for c in chunks if c.metadata.get("kind") == "class"]
        assert len(classes) >= 1
        assert classes[0].symbol == "Post"
        assert classes[0].metadata.get("superclass") == "ApplicationRecord"

    def test_belongs_to_detection(self, parser_factory, rails_model_file):
        """Test that belongs_to associations are detected."""
        parser = parser_factory.create_parser(Language.RUBY)

        chunks = parser.parse_content(rails_model_file, "post.rb", FileId(1))

        # Find the Post class
        classes = [c for c in chunks if c.metadata.get("kind") == "class"]
        assert len(classes) >= 1

        post_class = classes[0]
        assert post_class.metadata.get("rails_model") is True
        assert "associations" in post_class.metadata

        associations = post_class.metadata["associations"]
        belongs_to_assocs = [a for a in associations if a["type"] == "belongs_to"]
        assert len(belongs_to_assocs) >= 1
        assert belongs_to_assocs[0]["name"] == "author"

    def test_has_many_detection(self, parser_factory, rails_model_file):
        """Test that has_many associations are detected."""
        parser = parser_factory.create_parser(Language.RUBY)

        chunks = parser.parse_content(rails_model_file, "post.rb", FileId(1))

        classes = [c for c in chunks if c.metadata.get("kind") == "class"]
        post_class = classes[0]

        associations = post_class.metadata.get("associations", [])
        has_many_assocs = [a for a in associations if a["type"] == "has_many"]
        assert len(has_many_assocs) >= 2  # comments and tags

        assoc_names = {a["name"] for a in has_many_assocs}
        assert "comments" in assoc_names
        assert "tags" in assoc_names

    def test_validates_detection(self, parser_factory, rails_model_file):
        """Test that validations are detected."""
        parser = parser_factory.create_parser(Language.RUBY)

        chunks = parser.parse_content(rails_model_file, "post.rb", FileId(1))

        classes = [c for c in chunks if c.metadata.get("kind") == "class"]
        post_class = classes[0]

        assert "validations" in post_class.metadata
        validations = post_class.metadata["validations"]
        assert len(validations) >= 2  # title and email validations

        validation_fields = {v.get("field") for v in validations if "field" in v}
        assert "title" in validation_fields
        assert "email" in validation_fields

    def test_callback_detection(self, parser_factory, rails_model_file):
        """Test that callbacks are detected."""
        parser = parser_factory.create_parser(Language.RUBY)

        chunks = parser.parse_content(rails_model_file, "post.rb", FileId(1))

        classes = [c for c in chunks if c.metadata.get("kind") == "class"]
        post_class = classes[0]

        assert "callbacks" in post_class.metadata
        callbacks = post_class.metadata["callbacks"]
        assert len(callbacks) >= 2  # before_save and after_create

        callback_types = {c["type"] for c in callbacks}
        assert "before_save" in callback_types
        assert "after_create" in callback_types

    def test_scope_detection(self, parser_factory, rails_model_file):
        """Test that scopes are detected."""
        parser = parser_factory.create_parser(Language.RUBY)

        chunks = parser.parse_content(rails_model_file, "post.rb", FileId(1))

        classes = [c for c in chunks if c.metadata.get("kind") == "class"]
        post_class = classes[0]

        assert "scopes" in post_class.metadata
        scopes = post_class.metadata["scopes"]
        assert len(scopes) >= 2  # published and recent

        scope_names = {s["name"] for s in scopes}
        assert "published" in scope_names
        assert "recent" in scope_names


class TestFileExtensions:
    """Test Ruby file extension handling."""

    def test_rb_extension(self, parser_factory):
        """Test .rb file extension."""
        assert Language.from_file_extension("test.rb") == Language.RUBY

    def test_rake_extension(self, parser_factory):
        """Test .rake file extension."""
        assert Language.from_file_extension("tasks.rake") == Language.RUBY

    def test_gemspec_extension(self, parser_factory):
        """Test .gemspec file extension."""
        assert Language.from_file_extension("mygem.gemspec") == Language.RUBY

    def test_jbuilder_extension(self, parser_factory):
        """Test .jbuilder file extension."""
        assert Language.from_file_extension("show.json.jbuilder") == Language.RUBY

    def test_gemfile(self, parser_factory):
        """Test Gemfile filename."""
        assert Language.from_file_extension("Gemfile") == Language.RUBY

    def test_rakefile(self, parser_factory):
        """Test Rakefile filename."""
        assert Language.from_file_extension("Rakefile") == Language.RUBY

    def test_capfile(self, parser_factory):
        """Test Capfile filename."""
        assert Language.from_file_extension("Capfile") == Language.RUBY
