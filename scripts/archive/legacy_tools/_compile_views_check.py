import compileall
import sys

ok1 = compileall.compile_dir('app/views', force=True, quiet=1)
ok2 = compileall.compile_dir('app/views/profile_sections', force=True, quiet=1)
print(f'compile_views: {ok1} compile_profile_sections: {ok2}')

