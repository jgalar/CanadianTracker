import jQuery from "jquery";
import "datatables.net";
require('datatables.net-bs5');

jQuery(() => {
    jQuery('#product-table').DataTable({
        ajax: { url: '/api/products', dataSrc: '' },
        columns: [
            {
                data: 'name',
                title: 'Name',
                render: (data, type, row, meta) => {
                    return '<a href="/products/' + row.code + '">' + data + '</a>';
                }
            },
            {
                data: 'code',
                title: 'Code'
            }
        ],
    });
});
