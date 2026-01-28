<div align="center">
  <img src="data/icons/hicolor/scalable/apps/org.gnome.Showtime.svg" width="128" height="128">

  # Video Player

  Watch without distraction

  <img src="data/screenshots/1.png">
</div>

The project follows the [GNOME Code of Conduct](https://conduct.gnome.org/).


Build instructions
```shell
cd /home/dnieto/Projects/showtime
flatpak-builder --force-clean --install --user build-dir build-aux/flatpak/org.gnome.Showtime.Devel.json
flatpak run --devel org.gnome.Showtime.Devel
flatpak run --devel --command=sh org.gnome.Showtime.Devel

cd /home/dnieto/Projects/showtime
flatpak-builder --force-clean build-dir build-aux/flatpak/org.gnome.Showtime.Devel.json
flatpak-builder --run build-dir build-aux/flatpak/org.gnome.Showtime.Devel.json showtime
cd /home/dnieto/Projects/showtime
flatpak-builder --run build-dir build-aux/flatpak/org.gnome.Showtime.Devel.json /bin/bash
``