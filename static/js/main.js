// main.js: small helpers for client-side behaviors
document.addEventListener('DOMContentLoaded', function(){
  if(window.lucide){
    window.lucide.createIcons();
  }
  // remove email error on input
  var emailInput = document.getElementById('emailInput');
  if(emailInput){
    emailInput.addEventListener('input', function(){
      document.getElementById('emailError').textContent = '';
      emailInput.classList.remove('input-error');
    });
  }

  document.querySelectorAll('.compare-item').forEach(function(item, index){
    item.style.animation = 'fade-up .35s ease ' + (index * 45) + 'ms both';
  });

  document.querySelectorAll('form').forEach(function(form){
    form.addEventListener('submit', function(event){
      if(event.defaultPrevented){
        return;
      }
      var submitButton = form.querySelector('button[type="submit"], button:not([type])');
      if(submitButton){
        submitButton.classList.add('is-submitting');
        submitButton.disabled = true;
        submitButton.textContent = 'Working...';
      }
    });
  });
});
