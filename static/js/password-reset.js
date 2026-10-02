/* One digit per field, with paste/autofill and keyboard navigation. */
(() => {
  const digits = value => value.replace(/[٠-٩۰-۹]/g, digit => String(digit.charCodeAt(0) - (digit <= '٩' ? 1632 : 1776))).replace(/[^0-9]/g, '');
  document.querySelectorAll('[data-otp-input]').forEach(group => {
    const fields = [...group.querySelectorAll('input')];
    const fill = (index, value) => {
      const code = digits(value);
      for (let offset = 0; offset < code.length && index + offset < fields.length; offset++) fields[index + offset].value = code[offset];
      fields[Math.min(fields.length - 1, index + code.length)]?.focus();
    };
    fields.forEach((field, index) => {
      field.addEventListener('focus', () => field.select());
      field.addEventListener('paste', event => {
        event.preventDefault();
        const code = digits(event.clipboardData.getData('text'));
        fill(code.length === fields.length ? 0 : index, code);
      });
      field.addEventListener('input', () => {
        const code = digits(field.value); field.value = code.slice(0, 1);
        if (code) fill(code.length === fields.length ? 0 : index, code);
      });
      field.addEventListener('keydown', event => {
        if (event.key === 'Backspace' && !field.value && index > 0) {
          event.preventDefault(); fields[index - 1].value = ''; fields[index - 1].focus();
        } else if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') {
          event.preventDefault(); fields[Math.max(0, Math.min(fields.length - 1, index + (event.key === 'ArrowLeft' ? -1 : 1)))]?.focus();
        }
      });
    });
  });
})();
