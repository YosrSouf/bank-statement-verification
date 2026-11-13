const reportContent = document.querySelector("#report-content");
const downloadReport = document.querySelector("#download-report");
const printReport = document.querySelector("#print-report");

if (reportContent && downloadReport) {
    downloadReport.addEventListener("click", () => {
        const html = `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Bank statement review</title>
<style>
body {
    font: 16px/1.6 Arial, sans-serif;
    max-width: 900px;
    margin: 40px auto;
    padding: 0 24px;
    color: #29273d;
}

.card {
    border: 1px solid #ddd;
    border-radius: 12px;
    padding: 20px;
    margin: 20px 0;
}

.badge {
    font-weight: bold;
}

.MET,
.PASS {
    color: #216444;
}

.NOT_MET,
.FAIL {
    color: #96324a;
}

blockquote {
    white-space: pre-wrap;
    overflow-wrap: anywhere;
    border-left: 3px solid #aaa;
    padding-left: 15px;
}

table {
    border-collapse: collapse;
    width: 100%;
}

td,
th {
    padding: 8px;
    border: 1px solid #ddd;
}

@media print {
    body {
        margin: 0;
    }

    .card {
        break-inside: avoid;
    }
}
</style>
</head>
<body>${reportContent.innerHTML}</body>
</html>`;

        const blob = new Blob(
            [html],
            { type: "text/html;charset=utf-8" }
        );

        const url = URL.createObjectURL(blob);
        const link = document.createElement("a");

        link.href = url;
        link.download = "bank-statement-report.html";

        document.body.appendChild(link);
        link.click();
        link.remove();

        setTimeout(() => URL.revokeObjectURL(url), 1000);
    });
}

if (printReport) {
    printReport.addEventListener("click", () => {
        window.print();
    });
}