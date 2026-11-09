document.addEventListener('DOMContentLoaded', () => {
  const support = document.getElementById('whatsappFloatingWrapper');
  if (support && window.matchMedia('(max-width: 767.98px)').matches) {
    support.classList.add('is-minimized');
  }
  document.querySelectorAll('main .table-responsive table').forEach(table => {
    const headers = Array.from(table.querySelectorAll('thead th'), cell => cell.textContent.trim());
    if (!headers.length) return;
    table.classList.add('mobile-card-table');
    table.querySelectorAll('tbody tr').forEach(row => {
      Array.from(row.cells).forEach((cell, index) => {
        if (!cell.hasAttribute('colspan')) cell.dataset.label = headers[index] || '';
      });
    });
  });
  const result = document.getElementById('free-lookup-result');
  if (result) result.focus({preventScroll: true});
});
