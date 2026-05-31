(function () {
  var forms = Array.prototype.slice.call(document.querySelectorAll('form[action="/publicwhip/search"], form[action="/publicwhip/mps"]'));
  if (!forms.length) return;

  forms.forEach(function (form) {
    var input = form.querySelector('input[name="q"]');
    if (!input) return;
    if (input.dataset.acBound === '1') return;
    input.dataset.acBound = '1';

    form.classList.add('pw-ac-wrap');

    var list = document.createElement('div');
    list.className = 'pw-ac-list';
    list.hidden = true;
    form.appendChild(list);

    var items = [];
    var activeIndex = -1;
    var timer = null;

    function closeList() {
      list.hidden = true;
      list.innerHTML = '';
      items = [];
      activeIndex = -1;
    }

    function render(results) {
      list.innerHTML = '';
      items = [];
      activeIndex = -1;
      if (!results || !results.length) {
        list.hidden = true;
        return;
      }
      results.slice(0, 8).forEach(function (r, idx) {
        var btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'pw-ac-item';
        btn.dataset.index = String(idx);
        var meta = [r.party || '', r.constituency || ''].filter(Boolean).join(' · ');
        btn.innerHTML =
          '<span class="pw-ac-name">' + (r.name || '') + '</span>' +
          '<span class="pw-ac-meta">' + (meta || 'MP record') + '</span>';
        btn.addEventListener('mousedown', function (e) {
          e.preventDefault();
          input.value = r.name || input.value;
          closeList();
          form.submit();
        });
        list.appendChild(btn);
        items.push(btn);
      });
      list.hidden = false;
    }

    function setActive(next) {
      if (!items.length) return;
      if (activeIndex >= 0 && items[activeIndex]) items[activeIndex].classList.remove('is-active');
      activeIndex = next;
      if (activeIndex >= 0 && items[activeIndex]) items[activeIndex].classList.add('is-active');
    }

    async function fetchSuggestions(q) {
      var resp = await fetch('/api/mps/search?q=' + encodeURIComponent(q), { credentials: 'same-origin' });
      if (!resp.ok) return [];
      var data = await resp.json();
      return Array.isArray(data.results) ? data.results : [];
    }

    input.addEventListener('input', function () {
      var q = (input.value || '').trim();
      if (timer) clearTimeout(timer);
      if (q.length < 2) {
        closeList();
        return;
      }
      timer = setTimeout(async function () {
        try {
          var results = await fetchSuggestions(q);
          render(results);
        } catch (_err) {
          closeList();
        }
      }, 150);
    });

    input.addEventListener('keydown', function (e) {
      if (list.hidden || !items.length) return;
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        setActive(Math.min(activeIndex + 1, items.length - 1));
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        setActive(Math.max(activeIndex - 1, 0));
      } else if (e.key === 'Enter' && activeIndex >= 0) {
        e.preventDefault();
        items[activeIndex].dispatchEvent(new MouseEvent('mousedown', { bubbles: true }));
      } else if (e.key === 'Escape') {
        closeList();
      }
    });

    input.addEventListener('blur', function () {
      setTimeout(closeList, 120);
    });
  });
})();
