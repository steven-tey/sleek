from mailchimp3 import MailChimp
from flask import Flask, redirect, url_for, render_template, request
from string import Template
from airtable import Airtable
import stripe
import requests
import json
from apscheduler.schedulers.background import BackgroundScheduler
import atexit
from datetime import date

def add_product():

	airtable = Airtable('YOUR_AIRTABLE_BASE_KEY', 'domains', api_key='YOUR_AIRTABLE_API_KEY')

	domain_list = airtable.get_all(view='new', max_records=2)
	domainA = domain_list[0]['fields']['domain']
	priceA = domain_list[0]['fields']['price']
	domainB = domain_list[1]['fields']['domain']
	priceB = domain_list[1]['fields']['price']
	
	stripe.api_key = "YOUR_STRIPE_API_KEY"

	prod_A_id = stripe.Product.create(name=domainA, type="good")["id"]
	price_id_A = stripe.Price.create(
	  unit_amount=priceA*100,
	  currency="usd",
	  product=prod_A_id,
	)["id"]

	recordA = {'domain': domainA, 'price_id': price_id_A, 'listed': True}
	airtable.update_by_field('domain', domainA, recordA)

	with open(domainA+".txt", "w") as f:
		f.write("")

	prod_B_id = stripe.Product.create(name=domainB, type="good")["id"]
	price_id_B = stripe.Price.create(
	  unit_amount=priceB*100,
	  currency="usd",
	  product=prod_B_id,
	)["id"]

	recordB = {'domain': domainB, 'price_id': price_id_B, 'listed': True}
	airtable.update_by_field('domain', domainB, recordB)

	with open(domainB+".txt", "w") as f:
		f.write("")

	return domainA, priceA, domainB, priceB
	

def send_newsletter():
	'''
	Function that customizes and sends the newsletter to Mailchimp audience.
	
	Parameters:
	- domainA: first domain name
	- priceA price of first domain
	- domainB: second domain name
	- priceB: price of second domain

	'''
	try:
		domainA, priceA, domainB, priceB = add_product()
		mp = MailChimp(mc_api='YOUR_MAILCHIMP_API_KEY', mc_user='YOUR_MAILCHIMP_USERNAME')

		my_list_id = 'YOUR_MAILCHIMP_LIST_ID'
		subject_line = "New Domains"
		reply_to = "vanderheyden.robin@gmail.com"
		from_name = "Robin Vander Heyden"
		calendar_date = date.today().strftime("%B %d, %Y")

		campaign = mp.campaigns.create(data={'recipients': {'list_id': my_list_id}, 'settings': {'subject_line': subject_line, 'reply_to': reply_to, 'from_name': from_name}, "type": "regular"})

		#template = mp.templates.get(template_id='10007494')

		urlA = 'https://www.sleek.domains/' + domainA
		urlB = 'https://www.sleek.domains/' + domainB

		index = open('email.html', 'r').read()
		stemplate = Template(str(index))

		mp.campaigns.content.update(campaign_id=campaign['id'], data={'message': "campaign message", 'html': stemplate.safe_substitute(date=calendar_date, domainA=domainA, priceA="$"+str(priceA), urlA=urlA, domainB=domainB, priceB="$"+str(priceB), urlB=urlB)})

		mp.campaigns.actions.send(campaign_id=campaign['id'])

	except:
		print("No new domains found!")

# scheduler = BackgroundScheduler({'apscheduler.timezone': 'UTC'})
# scheduler.add_job(send_newsletter, "cron", day="*", hour=13, minute=0)
# scheduler.start()

# Shut down the scheduler when exiting the app
# atexit.register(lambda: scheduler.shutdown())


app = Flask(__name__, template_folder='templates')
app.url_map.strict_slashes = False

@app.route('/')
def main():
	return render_template('index.html', **locals())

@app.route('/subscribe', methods = ['POST'])
def subscribe():
	email = request.form['email']
	time = request.form['time']
	airtable = Airtable('YOUR_AIRTABLE_BASE_KEY', 'newsletter', api_key='YOUR_AIRTABLE_API_KEY')
	airtable.insert({'email': email, 'when': time})
	mailchimp = MailChimp(mc_api='YOUR_MAILCHIMP_API_KEY', mc_user='YOUR_MAILCHIMP_USERNAME')
	mailchimp.lists.members.create(list_id='YOUR_MAILCHIMP_LIST_ID', data={'email_address': email, 'status': 'pending'})

@app.route('/subscribed')
def subscribed():
	return render_template('subscribed.html', **locals())

@app.route('/<domain>')
def display_domain(domain):
	airtable = Airtable('YOUR_AIRTABLE_BASE_KEY', 'domains', api_key='YOUR_AIRTABLE_API_KEY')
	try: 
		airtable.search('domain', domain)
		try:
			airtable.search('domain', domain)[0]['fields']['sold']
			price_info = "Sold Out"
			return render_template('domains.html', **locals())
		except:
			price_info = "$" + str(airtable.search('domain', domain)[0]['fields']['price'])
			return render_template('domains.html', **locals())
	except:	
		return redirect(url_for('error'), code=302)

@app.route('/not-available')
def error():
	return render_template('error.html', **locals())

@app.route('/<domain>/pay')
def stripe_pay(domain):

	airtable = Airtable('YOUR_AIRTABLE_BASE_KEY', 'domains', api_key='YOUR_AIRTABLE_API_KEY')
	price_ID = airtable.search('domain', domain)[0]['fields']['price_id']

	stripe.api_key = "YOUR_STRIPE_API_KEY"
	session = stripe.checkout.Session.create(
		success_url=url_for('thanks', _external=True)+ '?session_id={CHECKOUT_SESSION_ID}',
		cancel_url=url_for('display_domain', domain=domain, _external=True),
		payment_method_types=["card"],
		line_items=[
			{
			"price": price_ID,
			"quantity": 1,
			},
		],
		mode="payment",
	)

	try:
		with open(domain+".txt", "a") as f:
			f.write(session['payment_intent'])
			f.write("\n")
	except:
		print("Whoops, file not found!")

	return {
        'checkout_session_id': session['id'], 
        'checkout_public_key': "pk_live_NnhBxhSwnX9L0uvDyKy0iMUO"
    }

@app.route('/thanks')
def thanks():
	return render_template('thanks.html')	

@app.route('/stripe_webhook', methods=['POST'])
def stripe_webhook():
	print('webhook called')
	if request.content_length > 1024 * 1024:
		print('REQUEST TOO BIG')
		abort(400)

	payload = request.get_data()
	sig_header = request.environ.get('HTTP_STRIPE_SIGNATURE')
	endpoint_secret = 'YOUR_STRIPE_SECRET_ENDPOINT'
	event = None

	try:
		event = stripe.Webhook.construct_event(
			payload, sig_header, endpoint_secret
		)
	except ValueError as e:
		# Invalid payload
		print('INVALID PAYLOAD')
		return {}, 400
	except stripe.error.SignatureVerificationError as e:
		# Invalid signature
		print('INVALID SIGNATURE')
		return {}, 400

	# Handle the checkout.session.completed event
	if event['type'] == 'checkout.session.completed':
		stripe.api_key = "YOUR_STRIPE_API_KEY"
		session = event['data']['object']
		line_items = stripe.checkout.Session.list_line_items(session['id'], limit=1)
		
		try:
			for line in list(open(line_items['data'][0]['description']+".txt")):
				try:
					stripe.PaymentIntent.cancel(
						line.rstrip(),
					)
				except:
					continue
		except:
			print("Oops, no file found!")

		airtable = Airtable('YOUR_AIRTABLE_BASE_KEY', 'domains', api_key='YOUR_AIRTABLE_API_KEY')
		record = {'domain': line_items['data'][0]['description'], 'sold': True}
		airtable.update_by_field('domain', line_items['data'][0]['description'], record)
	return {}

@app.route('/sitemap.xml')
def site_map():
    return render_template('sitemap.xml', base_url='https://www.sleek.domains/')

@app.route('/robots.txt')
def robots_txt():
    return render_template('robots.txt', base_url='https://www.sleek.domains/')
