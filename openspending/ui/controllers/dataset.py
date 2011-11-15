import logging

from pylons import request, response, tmpl_context as c
from pylons.controllers.util import redirect
from pylons.i18n import _
from colander import Invalid

from openspending import model
from openspending.model import Dataset, meta as db
from openspending.plugins.core import PluginImplementations
from openspending.plugins.interfaces import IDatasetController
from openspending.lib.csvexport import write_csv
from openspending.lib.jsonexport import to_jsonp
from openspending.lib import json
from openspending.ui.lib import helpers as h
from openspending.ui.lib.base import BaseController, render, abort
from openspending.ui.lib.browser import Browser
from openspending.ui.lib.views import View, ViewState, handle_request
from openspending.ui.lib.color import rgb_rainbow
from openspending.validation.model.currency import CURRENCIES
from openspending.validation.model.dataset import dataset_schema
from openspending.validation.model.common import ValidationState


log = logging.getLogger(__name__)

class DatasetController(BaseController):

    extensions = PluginImplementations(IDatasetController)

    model = model.Dataset

    def index(self, format='html'):
        c.results = model.Dataset.all_by_account(c.account)
        for item in self.extensions:
            item.index(c, request, response, c.results)

        if format == 'json':
            return to_jsonp(map(lambda d: d.as_dict(),
                                c.results))
        elif format == 'csv':
            results = map(lambda d: d.as_dict(), c.results)
            return write_csv(results, response)
        else:
            return render('dataset/index.html')

    def new(self, errors={}):
        c.currencies = sorted(CURRENCIES.items(), key=lambda (k,v): v)
        return render('dataset/new.html', form_errors=errors,
                form_fill=request.params if errors else None)

    def create(self):
        try:
            model = {'dataset': request.params}
            schema = dataset_schema(ValidationState(model))
            data = schema.deserialize(request.params)
            dataset = Dataset({'dataset': data})
            dataset.private = True
            db.session.add(dataset)
            db.session.commit()
            redirect(h.url_for(controller='dataset', action='view', 
                               dataset=dataset.name))
        except Invalid, i:
            errors = i.asdict()
            return self.new(errors)

    def view(self, dataset, format='html'):
        self._get_dataset(dataset)
        c.num_entries = len(c.dataset)

        handle_request(request, c, c.dataset)

        if c.view is None:
            url = h.url_for(controller='entry', action='index',
                        dataset=c.dataset.name)
            c.browser = Browser(c.dataset, request.params, url=url)
            c.browser.facet_by_dimensions()

        for item in self.extensions:
            item.read(c, request, response, c.dataset)

        if format == 'json':
            return to_jsonp(c.dataset.as_dict())
        elif format == 'csv':
            return write_csv([c.dataset.as_dict()], response)
        else:
            return render('dataset/view.html')

    def explorer(self, dataset):
        self._get_dataset(dataset)
        c.dataset_name = c.dataset.name
        return render('dataset/explorer.html')

    def model(self, dataset, format='json'):
        self._get_dataset(dataset)
        return to_jsonp(c.dataset.data)

    def timeline(self, name):
        self._get_dataset(name)
        c.dataset = model.Dataset.by_name(name)
        view = View.by_name(c.dataset, "default")
        viewstate = ViewState(c.dataset, view, None)
        data = []
        meta = []
        for entry, year_data in viewstate.aggregates:
            meta.append({"label": entry.get("label"),
                         "description": entry.get("description", ""),
                         "name": entry.get("name"),
                         "index": len(meta),
                         "taxonomy": entry.get("taxonomy")})
            sorted_year_data = sorted(year_data.items(), key=lambda kv: kv[0])
            data.append([{"x": k, "y": v,
                          "meta": len(meta) - 1} for
                         k, v in sorted_year_data])
        c.data = json.dumps(data)
        c.meta = json.dumps(meta)
        return render('dataset/timeline.html')

