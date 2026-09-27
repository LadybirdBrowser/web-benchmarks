#!/usr/bin/env python3
"""Tests for layout.py: which symbols an order file lists, how an order is drawn from a seed, and the flags and the
command a relink runs."""
import unittest

import layout

MACHO_NM = """_main T 100003f50 0
_f1 T 100003f00 0
__ZL6helperv t 100003e00 0
_table D 100008000 0
_lock S 100009000 0
"""

ELF_NM = """main T 210 0
_Z3foov W 220 10
helper.llvm.11828950255290167763 t 230 8
$x.0 t 200 0
$d.1 r 300 0
counter B 400 4
"""

LINK = (": && /usr/bin/c++ -O3 -flto=thin main.cpp.o -o bin/Ladybird.app/Contents/MacOS/WebContent "
        "-Wl,-rpath,/b/vcpkg_installed/lib lib/liblagom-web.a && cd /b/Services/WebContent && codesign -s - -f "
        "-o runtime --entitlements WebContent.entitlements /b/bin/Ladybird.app/Contents/MacOS/WebContent")


class TextSymbols(unittest.TestCase):
    def test_mach_o_code_symbols_keep_their_leading_underscore(self):
        self.assertEqual(layout.text_symbols(MACHO_NM), {"_main", "_f1", "__ZL6helperv"})

    def test_elf_weak_definitions_are_code_but_mapping_symbols_are_not(self):
        self.assertEqual(layout.text_symbols(ELF_NM), {"main", "_Z3foov", "helper.llvm.11828950255290167763"})

    def test_lines_that_are_not_symbols_are_ignored(self):
        self.assertEqual(layout.text_symbols("WebContent:\nnm: warning: no symbols\n\n"), set())


class OrderForSeed(unittest.TestCase):
    SYMBOLS = {f"_f{i}" for i in range(200)}

    def test_the_same_seed_draws_the_same_order(self):
        self.assertEqual(layout.order_for_seed(self.SYMBOLS, 7), layout.order_for_seed(set(self.SYMBOLS), 7))

    def test_another_seed_draws_another_order(self):
        self.assertNotEqual(layout.order_for_seed(self.SYMBOLS, 7), layout.order_for_seed(self.SYMBOLS, 8))

    def test_the_order_is_drawn_rather_than_sorted(self):
        self.assertNotEqual(layout.order_for_seed(self.SYMBOLS, 7), sorted(self.SYMBOLS))

    def test_every_symbol_is_listed_exactly_once(self):
        self.assertEqual(sorted(layout.order_for_seed(self.SYMBOLS, 7)), sorted(self.SYMBOLS))

    def test_the_other_names_listed_do_not_change_where_a_name_goes(self):
        # So a function only one arm defines can't reshuffle every other function's place.
        dropped = {"_f3", "_f150"}
        full = layout.order_for_seed(self.SYMBOLS, 7)
        self.assertEqual([name for name in full if name not in dropped],
                         layout.order_for_seed(self.SYMBOLS - dropped, 7))


class RoundSeed(unittest.TestCase):
    def test_no_two_binaries_in_a_run_share_an_order(self):
        seeds = [layout.round_seed(42, arm, index) for arm in ("base", "head") for index in range(1, 9)]
        self.assertEqual(len(set(seeds)), len(seeds))

    def test_the_run_seed_alone_reproduces_every_round(self):
        self.assertEqual(layout.round_seed(42, "head", 3), layout.round_seed(42, "head", 3))
        self.assertNotEqual(layout.round_seed(42, "head", 3), layout.round_seed(43, "head", 3))

    def test_any_run_seed_gives_a_usable_order_seed(self):
        for run_seed in (-5, 0, 2 ** 70):
            layout.order_for_seed({"_a", "_b"}, layout.round_seed(run_seed, "base", 1))


class LinkerFlags(unittest.TestCase):
    def test_macos_spells_the_cache_and_the_order_for_apple_s_ld(self):
        flags = layout.linker_flags("Darwin", "/cache", "/order.txt")
        self.assertIn("-Wl,-cache_path_lto,/cache", flags)
        self.assertIn("-Wl,-order_file,/order.txt", flags)

    def test_linux_spells_them_for_lld_and_quiets_the_names_an_executable_lacks(self):
        flags = layout.linker_flags("Linux", "/cache", "/order.txt")
        self.assertIn("-Wl,--thinlto-cache-dir=/cache", flags)
        self.assertIn("-Wl,--symbol-ordering-file=/order.txt", flags)
        self.assertIn("-Wl,--no-warn-symbol-ordering", flags)

    def test_a_default_order_relink_still_goes_through_the_cache(self):
        for system in ("Darwin", "Linux"):
            flags = layout.linker_flags(system, "/cache")
            self.assertTrue(any("/cache" in flag for flag in flags))
            self.assertFalse(any("order" in flag for flag in flags))


class UnsupportedLinker(unittest.TestCase):
    def test_apple_s_ld_takes_an_order_file(self):
        self.assertIsNone(layout.unsupported_linker("Darwin", LINK))

    def test_lld_takes_an_order_file(self):
        self.assertIsNone(layout.unsupported_linker("Linux", ": && clang++ -fuse-ld=lld a.o -o bin/Ladybird && :"))

    def test_any_other_linux_linker_is_refused_by_name(self):
        mold = layout.unsupported_linker("Linux", "clang++ -fuse-ld=mold a.o -o bin/Ladybird")
        self.assertIn("mold", mold)
        self.assertIn("--fixed-layout", mold)
        self.assertIn("default linker", layout.unsupported_linker("Linux", "g++ a.o -o bin/Ladybird"))


class WithFlags(unittest.TestCase):
    def test_the_flags_reach_the_link_and_not_the_codesign_after_it(self):
        command = layout.with_flags(LINK, "bin/Ladybird.app/Contents/MacOS/WebContent", ["-Wl,-order_file,/o.txt"])
        link, _, sign = command.partition("codesign")
        self.assertIn("-Wl,-order_file,/o.txt -o bin/Ladybird.app/Contents/MacOS/WebContent ", link)
        self.assertNotIn("order_file", sign)

    def test_a_flag_with_a_space_in_it_is_quoted(self):
        command = layout.with_flags("c++ a.o -o bin/Ladybird", "bin/Ladybird", ["-Wl,-order_file,/my dir/o.txt"])
        self.assertEqual(command, "c++ a.o '-Wl,-order_file,/my dir/o.txt' -o bin/Ladybird")

    def test_an_output_that_only_prefixes_the_real_one_does_not_match(self):
        with self.assertRaises(ValueError):
            layout.with_flags("c++ a.o -o bin/Ladybird.app/Contents/MacOS/Ladybird", "bin/Ladybird", ["-x"])

    def test_a_command_that_makes_something_else_is_refused(self):
        with self.assertRaises(ValueError):
            layout.with_flags("c++ a.o -o bin/Other", "bin/Ladybird", ["-x"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
