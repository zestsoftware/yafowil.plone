from collections import OrderedDict
from operator import attrgetter
from plone.autoform.interfaces import MODES_KEY
from plone.autoform.interfaces import WIDGETS_KEY
from plone.autoform.widgets import ParameterizedWidget
from plone.supermodel.interfaces import DEFAULT_ORDER
from plone.supermodel.interfaces import FIELDSETS_KEY
from plone.supermodel.utils import mergedTaggedValueDict
from plone.supermodel.utils import mergedTaggedValueList
from Products.CMFPlone import PloneMessageFactory as _
from zope.dottedname.resolve import resolve
from zope.schema import getFieldNamesInOrder

import six


class Fieldset(object):
    """Represent form fieldsets defined via ``plone.supermodel.model.fieldset``.
    All schema fields with no dedicated fieldset defined will end up in default
    fieldset.
    """

    def __init__(self, name, label=None, description=None, order=DEFAULT_ORDER):
        """Create fieldset.

        :param name: Fieldset name.
        :param label: Fieldset label.
        :param description: Fieldset description.
        :param order: Fieldset order.
        """
        self.name = name
        self.label = label
        self.description = description
        self.order = order
        self._children = list()

    def add(self, child):
        """Add field to fieldset.

        :param child: ``yafowil.plone.autoform.schema.Field`` or
            ``yafowil.plone.autoform.schema.Fieldset`` instance.
        """
        self._children.append(child)

    def __iter__(self):
        """Iterate over fields in order.

        :return: children iterator.
        """
        return self._children.__iter__()

    @property
    def children(self):
        return self._children


class Field(object):
    """Hold information about a field of a schema. Contained in ``Fieldset``
    instances.

    ``Field`` instances get passed to ``yafowil.plone.autoform.widget_factory``
    callbacks which are responsible to create and return ``yafowil.base.Widget``
    instances via ``yafowil.base.factory``.
    """

    def __init__(self, name, schema, widget=None, mode='edit', is_behavior=False):
        """Create field.

        :param name: Name of the field.
        :param schema: ``plone.supermodel.model.Schema`` instance.
        :param widget: ``yafowil.plone.autoform.schema.Widget`` instance
        :param mode: Form widget rendering mode as string. Either 'edit',
            'display' or 'skip'
        :param is_behavior: Flag whether field belongs to a dexterity behavior.
        """
        self.name = name
        self.schema = schema
        self.widget = widget
        self.mode = mode
        self.is_behavior = is_behavior
        # convenience
        self.schemafield = schema[name]
        self.label = self.schemafield.title
        self.help = self.schemafield.description
        self.required = self.schemafield.required
        # XXX: set convenience attributes if overwritten via widget.params


class Widget(object):
    """Hold information about ``plone.autoform.widgets.ParameterizedWidget``
    instances set via ``plone.autoform.directives.widget`` directive on schema
    fields. This information gets set on ``Field`` instances to gain information
    about the ``z3c.form`` widget used for this field.

    ``plone.autoform.directives.widget`` directive is not desired on schemata
    dedicated to yafowil forms, but used to interpret ``z3c.form`` related
    schemata with ``yafowil.plone.autoform``.
    """

    def __init__(self, factory=None, params=dict()):
        """Create widget.

        :param factory: ``ParameterizedWidget.widget_factory`` value.
        :param params: ``ParameterizedWidget.params`` value.
        """
        self.factory = factory
        self.params = params


def resolve_fieldset(fieldsets, schema_fieldset):
    """Get or create ``Fieldset`` instance for given ``schema_fieldset``.

    :param fieldsets: Dict containing the fieldsets
    :param schema_fieldset: Single schema fieldset definition from list
        returned by ``mergedTaggedValueList(schema, FIELDSETS_KEY)``
    :return: ``yafowil.plone.autoform.schema.Fieldset`` instance.
    """
    name = schema_fieldset.__name__
    label = schema_fieldset.label
    description = schema_fieldset.description
    order = schema_fieldset.order
    # case new fieldset
    if name not in fieldsets:
        fieldset = fieldsets[name] = Fieldset(
            name=name,
            label=label,
            description=description,
            order=order
        )
    # case fieldset exists
    else:
        fieldset = fieldsets[name]
        # case label changes
        if (label != fieldset.label and label != fieldset.name):
            fieldset.label = label
        # case description changes
        if description is not None:
            fieldset.description = description
        # case order changes
        if order != DEFAULT_ORDER:
            fieldset.order = order
    return fieldset


def resolve_widget(schema_widget):
    """Create and return ``Widget`` instance from given ``schema_widget``

    :param schema_widget: Entry by field name from dict returned by
        ``mergedTaggedValueDict(schema, WIDGETS_KEY)``.
    :return: ``yafowil.plone.autoform.schema.Widget`` instance.
    """
    # no widget
    if not schema_widget:
        return None
    # case ParameterizedWidget instance
    if isinstance(schema_widget, ParameterizedWidget):
        return Widget(
            factory=schema_widget.widget_factory,
            params=schema_widget.params
        )
    # case dotted path to widget class
    if isinstance(schema_widget, six.string_types):
        return Widget(factory=resolve(schema_widget))
    raise RuntimeError('Unknown widget: {0}'.format(schema_widget))


# aliases from plone autoform widget modes to yafowil widget modes
mode_aliases = {
    'input': 'edit',
    'display': 'display',
    'hidden': 'skip'
}


def resolve_schemata(schemata):
    """Resolve list of schemata to fieldsets.

    :param schemata: list of schemata returned by
        ``plone.dexterity.utils.iterSchemata`` or
        ``plone.dexterity.utils.iterSchemataForType``.
    :return: list of ``yafowil.plone.autoform.schema.Fieldset`` instances.
    """
    # fieldset definitions
    fieldsets = OrderedDict()
    # create default fieldset, not resolved by plone.autoform
    fieldsets['default'] = Fieldset(
        name='default',
        label=_('label_schema_default', default='Default')
    )
    for idx, schema in enumerate(schemata):
        # assume first schema in list is main schema, all remaining are
        # behavior schemata
        is_behavior = idx != 0
        # collect annotated widgets for schema
        widgets = mergedTaggedValueDict(schema, WIDGETS_KEY)
        # get annotated widget modes for schema
        modes = {
            mode[1]: mode_aliases[mode[2]]
            for mode in mergedTaggedValueList(schema, MODES_KEY)
        }
        # XXX: omitted from plone.autoform.directives
        # XXX: read_permission from plone.autoform.directives
        # XXX: write_permission from plone.autoform.directives
        # XXX: order_before from plone.autoform.directives
        # XXX: order_after from plone.autoform.directives
        # collect all fields from schema and create ``Field`` instances
        fields = OrderedDict()
        for name in getFieldNamesInOrder(schema):
            fields[name] = Field(
                name=name,
                schema=schema,
                widget=resolve_widget(widgets.get(name)),
                mode=modes.get(name, 'edit'),
                is_behavior=is_behavior
            )
        # collect fieldsets from schema and add related fields
        schema_fieldsets = mergedTaggedValueList(schema, FIELDSETS_KEY)
        for schema_fieldset in schema_fieldsets:
            fieldset = resolve_fieldset(fieldsets, schema_fieldset)
            for field_name in schema_fieldset.fields:
                fieldset.add(fields.pop(field_name))
        # add remaining fields to default fieldset
        fieldset = fieldsets['default']
        for field in fields.values():
            fieldset.add(field)
    # return sorted fieldset
    return sorted(fieldsets.values(), key=attrgetter('order'))
