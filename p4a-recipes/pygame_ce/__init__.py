"""A python-for-android recipe for pygame-ce.

python-for-android ships a recipe for upstream pygame, pinned at 2.1.0 -- older
than the pygame-ce this game is developed against, and a different project. But
pygame-ce is a fork with the same build system: at its 2.5.8 tag it carries its
own ``buildconfig/Setup.Android.SDL2.in``, which is the one thing a pygame
Android recipe actually needs from the source tree. So this is the upstream
recipe pointed at the fork, which is all a recipe for a fork should be.

It lives here, vendored, rather than patched into p4a, so that the version this
game builds against is the version written in this file and not whatever p4a
happens to ship. buildozer finds it through ``p4a.local_recipes``.

This has not been built yet -- the toolchain is the next step -- so treat the
first ``buildozer android debug`` as the test of it.
"""

from os.path import join

from pythonforandroid.recipe import CompiledComponentsPythonRecipe
from pythonforandroid.toolchain import current_directory

__all__ = ["PygameCeRecipe"]


class PygameCeRecipe(CompiledComponentsPythonRecipe):
    """Builds pygame-ce from source for Android, against p4a's own SDL2."""

    name = "pygame_ce"
    version = "2.5.8"
    url = (
        "https://github.com/pygame-community/pygame-ce/archive/refs/tags/"
        "{version}.tar.gz"
    )
    #: pygame-ce installs the ``pygame`` package -- the import name is the
    #: whole point of it being a drop-in -- so this is what the app imports.
    site_packages_name = "pygame"

    depends = [
        "sdl2",
        "sdl2_image",
        "sdl2_mixer",
        "sdl2_ttf",
        "setuptools",
        "jpeg",
        "png",
    ]
    call_hostpython_via_targetpython = False  # because of setuptools
    install_in_hostpython = False

    def prebuild_arch(self, arch):
        super().prebuild_arch(arch)
        with current_directory(self.get_build_dir(arch.arch)):
            setup_template = open(
                join("buildconfig", "Setup.Android.SDL2.in")
            ).read()
            env = self.get_recipe_env(arch)
            env["ANDROID_ROOT"] = join(self.ctx.ndk.sysroot, "usr")

            png = self.get_recipe("png", self.ctx)
            png_lib_dir = join(png.get_build_dir(arch.arch), ".libs")
            png_inc_dir = png.get_build_dir(arch)

            jpeg = self.get_recipe("jpeg", self.ctx)
            jpeg_inc_dir = jpeg_lib_dir = jpeg.get_build_dir(arch.arch)

            sdl_mixer_includes = ""
            sdl2_mixer_recipe = self.get_recipe("sdl2_mixer", self.ctx)
            for include_dir in sdl2_mixer_recipe.get_include_dirs(arch):
                sdl_mixer_includes += f"-I{include_dir} "

            sdl2_image_includes = ""
            sdl2_image_recipe = self.get_recipe("sdl2_image", self.ctx)
            for include_dir in sdl2_image_recipe.get_include_dirs(arch):
                sdl2_image_includes += f"-I{include_dir} "

            setup_file = setup_template.format(
                sdl_includes=(
                    " -I"
                    + join(self.ctx.bootstrap.build_dir, "jni", "SDL", "include")
                    + " -L"
                    + join(self.ctx.bootstrap.build_dir, "libs", str(arch))
                    + " -L"
                    + png_lib_dir
                    + " -L"
                    + jpeg_lib_dir
                    + " -L"
                    + arch.ndk_lib_dir_versioned
                ),
                sdl_ttf_includes="-I"
                + join(self.ctx.bootstrap.build_dir, "jni", "SDL2_ttf"),
                sdl_image_includes=sdl2_image_includes,
                sdl_mixer_includes=sdl_mixer_includes,
                jpeg_includes="-I" + jpeg_inc_dir,
                png_includes="-I" + png_inc_dir,
                freetype_includes="",
            )
            open("Setup", "w").write(setup_file)

    def get_recipe_env(self, arch):
        env = super().get_recipe_env(arch)
        env["USE_SDL2"] = "1"
        env["PYGAME_CROSS_COMPILE"] = "TRUE"
        env["PYGAME_ANDROID"] = "TRUE"
        return env


recipe = PygameCeRecipe()
