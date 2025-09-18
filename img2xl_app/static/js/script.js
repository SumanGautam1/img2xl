function decodeUnicode(str) {
    return str.replace(/\\u([\dA-Fa-f]{4})/g, function (match, grp) {
        return String.fromCharCode(parseInt(grp, 16));
    }).replace(/\\n/g, "\n")
      .replace(/\\'/g, "'")
      .replace(/\\"/g, '"');
}

// Loop through each message
document.addEventListener("DOMContentLoaded", function () {
    let index = 1;
    while (document.getElementById(`markdown-data-${index}`)) {
        const raw = document.getElementById(`markdown-data-${index}`).textContent;
        const decoded = decodeUnicode(raw);
        document.getElementById(`output-${index}`).innerHTML = marked.parse(decoded);
        index++;
    }
});