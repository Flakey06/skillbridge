(function () {
    "use strict";

    document.querySelectorAll(".toast-container .toast").forEach(function (toast) {
        window.setTimeout(function () {
            toast.remove();
        }, 5000);
    });
}());
