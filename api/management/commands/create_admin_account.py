from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError

from api.models import UserWorkspace, get_user_workspace


class Command(BaseCommand):
    help = 'Create or update a verified Kambyan admin account.'

    def add_arguments(self, parser):
        parser.add_argument('--email', required=True, help='Admin login email.')
        parser.add_argument('--name', default='System Admin', help='Admin display name.')
        parser.add_argument('--password', help='Admin password. Required when the account is new.')

    def handle(self, *args, **options):
        email = options['email'].strip().lower()
        name = options['name'].strip()
        password = options.get('password')

        if not email:
            raise CommandError('Email is required.')

        user = User.objects.filter(username=email).first()
        created = False

        if user is None:
            if not password:
                raise CommandError('Password is required for a new admin account.')
            user = User.objects.create_user(username=email, email=email, password=password, first_name=name)
            created = True
        else:
            user.email = email
            user.first_name = name or user.first_name
            if password:
                user.set_password(password)

        user.is_staff = True
        user.is_superuser = False
        user.is_active = True
        user.save()

        workspace = get_user_workspace(user)
        if workspace.role != UserWorkspace.Role.ADMIN:
            workspace.role = UserWorkspace.Role.ADMIN
            workspace.save(update_fields=['role'])

        action = 'Created' if created else 'Updated'
        self.stdout.write(self.style.SUCCESS('{} admin account: {}'.format(action, email)))
