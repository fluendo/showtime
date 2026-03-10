<div align="center">
  <img src="data/icons/hicolor/scalable/apps/org.gnome.Showtime.svg" width="128" height="128">

  # Video Player

  Watch without distraction

  <img src="data/screenshots/1.png">
</div>

The project follows the [GNOME Code of Conduct](https://conduct.gnome.org/).


Build and run Showtime with DSC
```shell
flatpak install gnome-nightly org.gnome.Platform//master org.gnome.Sdk//master
flatpak-builder --force-clean --install --user build-dir build-aux/flatpak/org.gnome.Showtime.Devel.json
flatpak run --env=DSC_KEY_STORE_PATH=<> --env=DSC_TRUST_STORE_PATH=<>  --devel org.gnome.Showtime.Devel
``
