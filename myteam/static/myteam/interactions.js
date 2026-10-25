/* Shared by Pages and the direct backend interface. */
window.bindActivityFeedback = function(root = document) {
  root.querySelectorAll('[data-activity-feedback]').forEach(form => {
    const choices = [...form.querySelectorAll('input[name="outcome"]')];
    const stars = [...form.querySelectorAll('input[name="rating"]')];
    function update() {
      const outcome = choices.find(input => input.checked)?.value;
      const yes = outcome === 'yes', no = outcome === 'no';
      form.querySelector('[data-rating-panel]').hidden = !yes;
      stars.forEach(input => { input.disabled = !yes; input.required = yes; });
      form.querySelector('[data-comment-panel]').hidden = !(yes || no);
      const comment = form.querySelector('textarea[name="comment"]');
      comment.disabled = !(yes || no); comment.required = no;
      form.querySelector('[data-comment-label]').textContent = no ? 'Почему не получилось?' : 'Комментарий (необязательно)';
      const selected = Number(stars.find(input => input.checked)?.value || 0);
      stars.forEach(input => input.closest('label').classList.toggle('selected', Number(input.value) <= selected));
    }
    choices.forEach(input => input.addEventListener('change', update));
    stars.forEach(input => input.addEventListener('change', update));
    update();
  });
};
