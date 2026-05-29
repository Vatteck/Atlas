import sys
sys.path.insert(0, '/home/vatteck/Projects/Atlas/atlas/gems/arch')

import atlas_rs

srcinfo = """
pkgbase = test-package
    pkgdesc = A test package
    url = https://example.com
    makedepends = gcc

pkgname = test-package
    depends = glibc
"""

res = atlas_rs.map_srcinfo(srcinfo, "test-package")
print(res)
