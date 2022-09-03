import jQuery from "jquery";
import Plotly from "plotly.js-basic-dist"

jQuery(() => {
    const code = jQuery('body').attr('data-sku-code');
    jQuery.get('/api/skus/' + code + '/samples').done(samples => {
        const xs = [];
        const ys = [];

        let i = 0;
        let lastPrice = 0;
        for (const sample of samples) {
            const time = sample.sample_time;
            const price = sample.product_info.price;

            /* Insert the last price to render changes as "steps". */
            if (i && price !== lastPrice) {
                xs.push(time);
                ys.push(lastPrice)
            }

            xs.push(time);
            ys.push(price);
            lastPrice = price;
            i++;
        }

        const div = jQuery('#price-history')[0];
        Plotly.newPlot(div, [{
            x: xs,
            y: ys,
            type: 'scatter',
            mode: 'lines+markers',
        }], {
            yaxis: {
                rangemode: 'tozero',
            },
        }
        );
    });
});
