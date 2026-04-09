/**
 * Inhaltsverzeichnis aus H1–H6 mit A5-Seitenzahlen (reine Schätzung im Viewport).
 *
 * Seiten werden aus der vertikalen Position relativ zum Inhaltsbereich und der
 * konfigurierbaren Seitenhöhe (Standard A5 Hochformat: 210 mm) berechnet.
 *
 * Nutzung:
 *   <div id="toc"></div>
 *   <main id="content">… Überschriften …</main>
 *   <script src="toc-a5.js"></script>
 *   <script>
 *     TocA5.init({ tocContainer: '#toc', contentRoot: '#content' });
 *   </script>
 */
(function (global) {
  'use strict';

  var CSS_MM_PER_IN = 25.4;
  var CSS_PX_PER_IN = 96;

  function mmToPx(mm) {
    return (mm * CSS_PX_PER_IN) / CSS_MM_PER_IN;
  }

  function resolveElement(target, fallback) {
    if (!target) return fallback;
    if (typeof target === 'string') return document.querySelector(target);
    if (target.nodeType === 1) return target;
    return null;
  }

  function ensureHeadingIds(headings, prefix) {
    var used = {};
    for (var i = 0; i < headings.length; i++) {
      var h = headings[i];
      var id = h.id;
      if (!id || used[id]) {
        var base = prefix + '-' + (i + 1);
        var candidate = base;
        var n = 0;
        while (document.getElementById(candidate) || used[candidate]) {
          n += 1;
          candidate = base + '-' + n;
        }
        h.id = candidate;
        id = candidate;
      }
      used[id] = true;
    }
  }

  /** Position des Elements relativ zum oberen Rand von `root` (Scrollbereich). */
  function offsetTopWithin(el, root) {
    var r = root.getBoundingClientRect();
    var e = el.getBoundingClientRect();
    return e.top - r.top + root.scrollTop;
  }

  function pageNumberForOffset(offsetPx, pageHeightPx, firstPageOffsetPx) {
    var rel = offsetPx - (firstPageOffsetPx || 0);
    if (rel < 0) rel = 0;
    return Math.floor(rel / pageHeightPx) + 1;
  }

  function buildListItem(heading, page, options) {
    var level = parseInt(heading.tagName.slice(1), 10);
    var li = document.createElement('li');
    li.className =
      options.classPrefix + '-item ' + options.classPrefix + '-level-' + level;

    var a = document.createElement('a');
    a.href = '#' + heading.id;
    a.className = options.classPrefix + '-link';

    var title = document.createElement('span');
    title.className = options.classPrefix + '-title';
    title.textContent = heading.textContent.replace(/\s+/g, ' ').trim();

    var pageSpan = document.createElement('span');
    pageSpan.className = options.classPrefix + '-page';
    pageSpan.textContent = String(page);
    pageSpan.setAttribute('aria-label', 'Seite ' + page);

    a.appendChild(title);
    a.appendChild(document.createTextNode(' '));
    a.appendChild(pageSpan);
    li.appendChild(a);
    return li;
  }

  function renderToc(container, headings, pages, options) {
    container.innerHTML = '';
    container.classList.add(options.classPrefix);

    var nav = document.createElement('nav');
    nav.className = options.classPrefix + '-nav';
    nav.setAttribute('aria-label', options.ariaLabel || 'Inhaltsverzeichnis');

    var ol = document.createElement('ol');
    ol.className = options.classPrefix + '-list';

    for (var i = 0; i < headings.length; i++) {
      ol.appendChild(buildListItem(headings[i], pages[i], options));
    }
    nav.appendChild(ol);
    container.appendChild(nav);
  }

  var defaultOptions = {
    tocContainer: '#toc',
    contentRoot: 'body',
    /** A5 Hochformat: Höhe 210 mm (nur für die Seitenzahl-Berechnung). */
    pageHeightMm: 210,
    /** Optional: fester Abstand vom Anfang des Inhalts bis zur „Seite 1“ (mm). */
    firstPageTopMarginMm: 0,
    headingSelector: 'h1, h2, h3, h4, h5, h6',
    headingIdPrefix: 'toc-heading',
    classPrefix: 'toc-a5',
    ariaLabel: 'Inhaltsverzeichnis',
    /** Mindestabstand unterhalb der letzten Überschrift, damit die Seitenzahl nicht „klebt“. */
    debounceMs: 100
  };

  function TocA5State() {
    this.options = null;
    this._scheduled = null;
    this._ro = null;
    this._onResize = null;
    this._onPrint = null;
  }

  TocA5State.prototype.update = function () {
    var o = this.options;
    if (!o) return;

    var root = o._contentRoot;
    var tocEl = o._tocEl;
    if (!root || !tocEl) return;

    var headings = Array.prototype.slice.call(
      root.querySelectorAll(o.headingSelector)
    );

    ensureHeadingIds(headings, o.headingIdPrefix);

    var pageHeightPx = mmToPx(o.pageHeightMm);
    var firstOffPx = mmToPx(o.firstPageTopMarginMm);

    var pages = headings.map(function (h) {
      var top = offsetTopWithin(h, root);
      return pageNumberForOffset(top, pageHeightPx, firstOffPx);
    });

    renderToc(tocEl, headings, pages, o);
  };

  TocA5State.prototype.scheduleUpdate = function () {
    var self = this;
    var ms = (this.options && this.options.debounceMs) || 100;
    if (this._scheduled) clearTimeout(this._scheduled);
    this._scheduled = setTimeout(function () {
      self._scheduled = null;
      self.update();
    }, ms);
  };

  TocA5State.prototype.destroy = function () {
    if (this._scheduled) {
      clearTimeout(this._scheduled);
      this._scheduled = null;
    }
    if (this._ro && this.options && this.options._contentRoot) {
      try {
        this._ro.disconnect();
      } catch (e) {}
      this._ro = null;
    }
    if (this._onResize) {
      window.removeEventListener('resize', this._onResize);
      this._onResize = null;
    }
    if (this._onPrint) {
      window.removeEventListener('beforeprint', this._onPrint);
      window.removeEventListener('afterprint', this._onPrint);
      this._onPrint = null;
    }
    this.options = null;
  };

  var state = new TocA5State();

  var api = {
    /**
     * @param {object} userOpts – siehe defaultOptions
     */
    init: function (userOpts) {
      api.destroy();

      var o = {};
      for (var k in defaultOptions) {
        if (Object.prototype.hasOwnProperty.call(defaultOptions, k)) {
          o[k] = defaultOptions[k];
        }
      }
      if (userOpts) {
        for (var j in userOpts) {
          if (Object.prototype.hasOwnProperty.call(userOpts, j)) {
            o[j] = userOpts[j];
          }
        }
      }

      o._tocEl = resolveElement(o.tocContainer, null);
      o._contentRoot = resolveElement(o.contentRoot, document.body);

      if (!o._tocEl) {
        console.warn('TocA5: tocContainer nicht gefunden.');
        return;
      }
      if (!o._contentRoot) {
        console.warn('TocA5: contentRoot nicht gefunden.');
        return;
      }

      state.options = o;

      state._onResize = function () {
        state.scheduleUpdate();
      };
      window.addEventListener('resize', state._onResize);

      state._onPrint = function () {
        state.update();
      };
      window.addEventListener('beforeprint', state._onPrint);
      window.addEventListener('afterprint', state._onPrint);

      if (typeof ResizeObserver !== 'undefined') {
        state._ro = new ResizeObserver(function () {
          state.scheduleUpdate();
        });
        state._ro.observe(o._contentRoot);
      }

      state.update();
    },

    refresh: function () {
      state.update();
    },

    destroy: function () {
      state.destroy();
    }
  };

  global.TocA5 = api;
})(typeof window !== 'undefined' ? window : globalThis);
