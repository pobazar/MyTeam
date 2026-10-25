/* Shared conditional fields; the Pages dialog uses explicit Yes/No action buttons. */
window.bindActivityFeedback = function(root = document) {
  root.querySelectorAll('[data-activity-feedback]').forEach(form => {
    const choices = [...form.querySelectorAll('input[name="outcome"]')];
    const hiddenChoice = choices.find(input => input.type === 'hidden');
    const stars = [...form.querySelectorAll('input[name="rating"]')];
    function update() {
      const outcome = hiddenChoice ? hiddenChoice.value : choices.find(input => input.checked)?.value;
      const yes = outcome === 'yes', no = outcome === 'no', chosen = yes || no;
      form.querySelector('[data-rating-panel]').hidden = !yes;
      stars.forEach(input => { input.disabled = !yes; input.required = yes; });
      form.querySelector('[data-comment-panel]').hidden = !chosen;
      const comment = form.querySelector('textarea[name="comment"]');
      comment.disabled = !chosen; comment.required = false;
      comment.placeholder = no ? 'Почему не получилось провести активность?' : 'Поделитесь впечатлениями';
      form.querySelector('[data-comment-label]').textContent = no ? 'Почему не получилось? (необязательно)' : 'Комментарий (необязательно)';
      const selected = Number(stars.find(input => input.checked)?.value || 0);
      stars.forEach(input => input.closest('label').classList.toggle('selected', Number(input.value) <= selected));
      if (hiddenChoice) {
        form.querySelector('[data-outcome-choice]').hidden = chosen;
        form.querySelector('[data-outcome-summary]').hidden = !chosen;
        form.querySelector('[data-outcome-label]').textContent = yes ? 'Активность проведена' : 'Не получилось провести активность';
        form.querySelector('[data-submit]').hidden = !chosen;
      }
    }
    form.querySelectorAll('[data-outcome]').forEach(button => button.onclick = () => {
      hiddenChoice.value = button.dataset.outcome; update();
      if (hiddenChoice.value === 'yes') (stars.find(input => input.checked) || stars[0])?.focus();
      else form.querySelector('[data-outcome-label]').focus({preventScroll:true});
    });
    const change = form.querySelector('[data-change-outcome]');
    if (change) change.onclick = () => { hiddenChoice.value = ''; update(); form.querySelector('[data-outcome]')?.focus(); };
    choices.forEach(input => input.addEventListener('change', update));
    stars.forEach(input => input.addEventListener('change', update));
    update();
  });
};
