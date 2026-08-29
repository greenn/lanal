document.querySelectorAll('.bars').forEach((bars) => {
  const count = Number(bars.dataset.count || 13);
  for (let i = 0; i < count; i += 1) {
    const bar = document.createElement('i');
    const height = 18 + ((i * 11) % 24);
    bar.style.height = `${height}px`;
    bars.appendChild(bar);
  }
});

document.querySelectorAll('.chevron').forEach((button) => {
  button.addEventListener('click', () => {
    const project = button.closest('.project');
    const open = project.classList.toggle('project-open');
    button.textContent = open ? '⌃' : '⌄';
  });
});

document.querySelectorAll('.nav a').forEach((link) => {
  link.addEventListener('click', (event) => {
    event.preventDefault();
    document.querySelectorAll('.nav a').forEach((item) => item.classList.remove('active'));
    link.classList.add('active');
  });
});
