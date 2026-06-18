from unittest import TestCase

from atlas.gems.arch.worker import compute_makepkg_optimizations

STOCK = (
    '#MAKEFLAGS="-j2"\n'
    '#COMPRESSXZ=(xz -c -z -)\n'
    'COMPRESSZST=(zstd -c -z -q -)\n'
    'BUILDENV=(!distcc color check !sign)\n'
)

FULLY_TUNED = (
    'MAKEFLAGS="-j16"\n'
    'COMPRESSXZ=(xz -c -z - --threads=0)\n'
    'COMPRESSZST=(zstd -c -z -q - --threads=0)\n'
    'BUILDENV=(!distcc color check !sign)\n'
)


class ComputeMakepkgOptimizationsTest(TestCase):

    def test_stock_makepkg_gets_all_optimizations(self):
        content, opts, skipped = compute_makepkg_optimizations(STOCK, ncpus=8, ccache_installed=False)
        self.assertIsNotNone(content)
        self.assertIn('MAKEFLAGS="-j$(nproc)"', opts)
        self.assertIn('COMPRESSXZ=(xz -c -z - --threads=0)', opts)
        self.assertIn('COMPRESSZST=(zstd -c -z -q - --threads=0)', opts)
        self.assertEqual([], skipped)
        # the directives we override are stripped from the base (re-appended by the caller)
        self.assertNotIn('MAKEFLAGS', content)
        self.assertNotIn('COMPRESSZST', content)

    def test_fully_tuned_makepkg_is_left_alone(self):
        content, opts, skipped = compute_makepkg_optimizations(FULLY_TUNED, ncpus=8, ccache_installed=False)
        self.assertIsNone(content)
        self.assertEqual([], opts)
        # all three customized directives are reported (for an INFO log), none overridden
        self.assertEqual(3, len(skipped))

    def test_missing_directives_still_apply_and_keep_content(self):
        # Regression: a makepkg.conf without the standard (commented) MAKEFLAGS/COMPRESS* lines used to
        # compute optimizations but then DROP them because the working copy was never initialised.
        bare = 'CFLAGS="-march=native"\nCXXFLAGS="-march=native"\n'
        content, opts, skipped = compute_makepkg_optimizations(bare, ncpus=8, ccache_installed=False)
        self.assertIsNotNone(content, 'optimizations must not be discarded when no directive line existed')
        self.assertEqual(bare, content, 'nothing matched → base content is the untouched input')
        self.assertIn('MAKEFLAGS="-j$(nproc)"', opts)
        self.assertIn('COMPRESSXZ=(xz -c -z - --threads=0)', opts)

    def test_no_cpus_skips_makeflags_only(self):
        content, opts, _ = compute_makepkg_optimizations(STOCK, ncpus=None, ccache_installed=False)
        self.assertNotIn('MAKEFLAGS="-j$(nproc)"', opts)        # no cpu count → no parallel flag
        self.assertIn('COMPRESSXZ=(xz -c -z - --threads=0)', opts)  # compression still optimized

    def test_ccache_enabled_when_installed_and_referenced(self):
        src = 'BUILDENV=(!distcc color !ccache check !sign)\n'
        content, opts, _ = compute_makepkg_optimizations(src, ncpus=8, ccache_installed=True)
        self.assertTrue(any('ccache' in o and '!ccache' not in o for o in opts),
                        'ccache should be enabled in the regenerated BUILDENV')
