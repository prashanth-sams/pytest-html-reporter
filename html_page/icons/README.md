# Icons

Font Awesome 4.7.0 glyphs, kept here as SVGs so a generated report renders its
icons without reaching out to a CDN.

- Source: [Font-Awesome-SVG-PNG](https://github.com/encharm/Font-Awesome-SVG-PNG)
  (`black/svg`), an SVG export of [Font Awesome](https://fontawesome.com) 4.7.0.
- Licence: CC BY 4.0 (icons), as per the Font Awesome 4.7.0 licence.

Each file keeps its Font Awesome name (`fa-home` -> `home.svg`) and is cropped
to the glyph's own outline, with the `viewBox` still giving that outline's place
on the font's 1792-unit em - the em Font Awesome drew on, with the baseline 1536
units down.

[`html_page/icon_styles.py`](../icon_styles.py) reads this directory at report
generation time and inlines every glyph into the page as a CSS mask. The
`viewBox` is what lets it rebuild the em box the font gave each icon and paint
the outline into its place inside it, so `<i class="fa fa-home"></i>` keeps
working, an icon still sizes itself to the text around it, and it still takes
its colour from `currentcolor`.

To add an icon, drop its SVG here named after the `fa-*` class; the stylesheet
picks it up automatically. Crop it to the outline first - an uncropped one is
drawn in the wrong place and at the wrong size.
