function openTab(tabName) {
  var x = document.getElementsByClassName("containerTab");
  var target = document.getElementById(tabName);
  var isAlreadyOpen = target && (target.style.display === "block" || window.getComputedStyle(target).display === "block");

  for (var i = 0; i < x.length; i++) {
    x[i].style.display = "none";
  }

  if (target && !isAlreadyOpen) {
    target.style.display = "block";
    target.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }
}

// Dropdwon button
/* When the user clicks on the button,
toggle between hiding and showing the dropdown content */
function myFunction() {
  document.getElementById("myDropdown").classList.toggle("show");
}

function filterFunction() {
  var input, filter, ul, li, a, i;
  input = document.getElementById("myInput");
  filter = input.value.toUpperCase();
  div = document.getElementById("myDropdown");
  a = div.getElementsByTagName("a");
  for (i = 0; i < a.length; i++) {
    txtValue = a[i].textContent || a[i].innerText;
    if (txtValue.toUpperCase().indexOf(filter) > -1) {
      a[i].style.display = "";
    } else {
      a[i].style.display = "none";
    }
  }
}
