var trigger = setInterval(function() { 
    if (document.getElementById('print-button') != null) {
        document.getElementById('print-button').addEventListener('click', () => {
            window.print()
         });
      clearInterval(trigger);
      console.log('Success');
    } else {
      console.log('Triggered');
    }
  }, 100);