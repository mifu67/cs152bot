# bot.py
import discord
from discord.ext import commands
import os
import json
import logging
import re
import requests
from report import Report
from inform import Colloquialism
import pdb
import unidecode
from unidecode import unidecode
from google_trans_new import google_translator  
import unidecode
from google.cloud import translate_v2 as translate
from googleapiclient import discovery
import os
os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = 'auth.json'

from google.cloud import translate_v2 as translate
translate_client = translate.Client()

from inference import predict_propoganda


import api_key
API_KEY = api_key.get_key()
perspective_client = discovery.build(
    "commentanalyzer",
    "v1alpha1",
    developerKey=API_KEY,
    discoveryServiceUrl="https://commentanalyzer.googleapis.com/$discovery/rest?version=v1alpha1",
    static_discovery=False,
)
# translate_client = translate.Client()

# Set up logging to the console
logger = logging.getLogger('discord')
logger.setLevel(logging.DEBUG)
handler = logging.FileHandler(filename='discord.log', encoding='utf-8', mode='w')
handler.setFormatter(logging.Formatter('%(asctime)s:%(levelname)s:%(name)s: %(message)s'))
logger.addHandler(handler)

# There should be a file called 'tokens.json' inside the same folder as this file
token_path = 'tokens.json'
if not os.path.isfile(token_path):
    raise Exception(f"{token_path} not found!")
with open(token_path) as f:
    # If you get an error here, it means your token is formatted incorrectly. Did you put it in quotes?
    tokens = json.load(f)
    discord_token = tokens['discord']

class ModBot(discord.Client):
    def __init__(self): 
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix='.', intents=intents)
        self.group_num = 13
        self.mod_channels = {} # Map from guild to the mod channel id for that guild
        self.reports = {} # Map from user IDs to the state of their report
        self.informs = {} # Map from user IDs to the state of their colloquialism informing
        self.report_id_to_author_id = {}
        self.next_assignable_id = 1
        self.inform_id_to_author_id = {}

    async def on_ready(self):
        print(f'{self.user.name} has connected to Discord! It is these guilds:')
        for guild in self.guilds:
            print(f' - {guild.name}')
        print('Press Ctrl-C to quit.')
        print('running branch justinfix')

        # Parse the group number out of the bot's name
        match = re.search('[gG]roup (\d+) [bB]ot', self.user.name)
        if match:
            self.group_num = match.group(1)
        else:
            raise Exception("Group number not found in bot's name. Name format should be \"Group # Bot\".")

        # Find the mod channel in each guild that this bot should report to
        for guild in self.guilds:
            for channel in guild.text_channels:
                if channel.name == f'group-{self.group_num}-mod':
                    self.mod_channels[guild.id] = channel
        

    async def on_message(self, message):
        '''
        This function is called whenever a message is sent in a channel that the bot can see (including DMs). 
        Currently the bot is configured to only handle messages that are sent over DMs or in your group's "group-#" channel. 
        '''
        # Ignore messages from the bot 
        if message.author.id == self.user.id:
            return

        # Check if this message was sent in a server ("guild") or if it's a DM
        if message.guild:
            await self.handle_channel_message(message)
        else:
            await self.handle_dm(message)
            
        # POTENTIAL ERROR FIX?
        # if message.guild:
        #     if message.channel.name == f'group-{self.group_num}-mod':
        #         await self.handle_mod_channel_message(message)
        #     else:
        #         await self.handle_channel_message(message)
        # else:
        #     await self.handle_dm(message)

    async def handle_dm(self, message):
        print("h")
        # Handle a help message
        if message.content == Report.HELP_KEYWORD:
            reply =  "Use the `report` command to begin the reporting process.\n"
            reply += "Use the `cancel` command to cancel the report process.\n"
            await message.channel.send(reply)
            return

        author_id = message.author.id
        responses = []

        #respond to messages if they're part of a reporting flow OR the inform flow
        
        
        if author_id in self.reports or message.content.startswith(Report.START_KEYWORD):
            if author_id not in self.reports and not message.content.startswith(Report.START_KEYWORD):
                return
            
            # If we don't currently have an active report/inform for this user, add one
            if author_id not in self.reports:
                self.reports[author_id] = Report(self, author_id,self.next_assignable_id)
                self.report_id_to_author_id[self.next_assignable_id] = author_id
                self.next_assignable_id += 1

            # Let the report/inform class handle this message; forward all the messages it returns to us
            if not self.reports[author_id].mod_review:
                responses = await self.reports[author_id].handle_message(message)
                for r in responses:
                    await message.channel.send(r)

                if self.reports[author_id].mod_review:
                    #initial mod flow
                    responses = await self.reports[author_id].mod_flow("")
                    mod_channel = self.mod_channels[self.reports[author_id].guild.id]
                    print(mod_channel.name)
                    for r in responses:
                        await mod_channel.send(r)
                        
            if self.reports[author_id].report_complete():
                self.reports.pop(author_id)



        #inform block
        if author_id in self.informs or message.content.startswith(Colloquialism.START_KEYWORD):
            if author_id not in self.informs and not message.content.startswith(Colloquialism.START_KEYWORD):
                return
            
            if author_id not in self.informs:
                self.informs[author_id] = Colloquialism(self, author_id,self.next_assignable_id)
                self.inform_id_to_author_id[self.next_assignable_id] = author_id
                self.next_assignable_id += 1


            if not self.informs[author_id].mod_review:
                responses = await self.informs[author_id].handle_message(message)
                for r in responses:
                    await message.channel.send(r)

                if self.informs[author_id].mod_review:
                    #initial mod flow
                    responses = await self.informs[author_id].mod_flow("")
                    mod_channel = self.mod_channels[self.informs[author_id].guild.id]
                    print(mod_channel.name)
                    for r in responses:
                        await mod_channel.send(r)

            if self.informs[author_id].inform_complete():
                self.informs.pop(author_id)

    async def handle_mod_channel_message(self, message):
        print("m")
        # Only handle messages sent in the "group-13-mod" channel
        if not message.channel.name == f'group-{self.group_num}-mod':
            print(message.channel.name)
            print(f'group-{self.group_num}-mod')
            print((not message.channel.name == f'group-{self.group_num}-mod'))
            return

        # Forward the message to the mod channel
        mod_channel = message.channel

        print("received")

        match = re.match(r'^(\d+):', message.content)
        if not match:
            await mod_channel.send("Message must start with report id or inform id (ex: 3:1)")
            return

        received_id = int(match.group()[:-1])

        if received_id not in self.report_id_to_author_id and received_id not in self.inform_id_to_author_id:
            await mod_channel.send(f"Could not find a report or inform with id {received_id}")
            return
        
        if received_id in self.report_id_to_author_id:
            author_id = self.report_id_to_author_id[received_id]
            responses = await self.reports[author_id].mod_flow(message)

        else:
            author_id = self.inform_id_to_author_id[received_id]
            responses = await self.informs[author_id].mod_flow(message)

        for r in responses:
            await mod_channel.send(r)


    async def handle_channel_message(self, message):
        if message.channel.name == f'group-{self.group_num}-mod':
            return await self.handle_mod_channel_message(message)
        
        # Only handle messages sent in the "group-#" channel
        if not message.channel.name == f'group-{self.group_num}':
            return

        #Check if any words in the message are in the list of colloquialisms.txt file, and if so flag the message and send it to the mod channel
        with open('colloquialisms.txt') as f:
            colloquialisms = f.readlines()
        colloquialisms = [x.strip() for x in colloquialisms]
        coll_present = False
        for word in message.content.split():
            if word in colloquialisms:
                coll_present = True
                break
        if coll_present:
            mod_channel = self.mod_channels[message.guild.id]
            await mod_channel.send(f'colloquialism detected:\n{message.author.name}: "{message.content}"')
            scores = self.eval_text(message.content)
            await mod_channel.send(self.code_format(scores))
            return
        
    

        # Forward the message to the mod channel
        mod_channel = self.mod_channels[message.guild.id]
        await mod_channel.send(f'Forwarded message:\n{message.author.name}: "{message.content}"')
        scores = self.eval_text(message.content)
        await mod_channel.send(self.code_format(scores))

    
    def eval_text(self, message):
        ascii_message = unidecode.unidecode(message)
        response = translate_client.translate(ascii_message, target_language='en')
        english_message = response['translatedText']
        processed_message = english_message.lower()

        likely_propoganda, propoganda_types = predict_propoganda(processed_message)

        analyze_request = {
            'comment': {'text': processed_message},
            'requestedAttributes': {'TOXICITY': {}}
        }
        response = perspective_client.comments().analyze(body=analyze_request).execute()
        toxicity_score = response['attributeScores']['TOXICITY']['summaryScore']['value']

        return processed_message, likely_propoganda, propoganda_types, toxicity_score

    def code_format(self, text):
        message, likely_propoganda, propoganda_types, toxicity_score = text
        reply =  "Evaluated: '" + message + "'\n"
        if likely_propoganda:
            reply += """```This message may contain misinformation or propoganda!```"""
            reply += f"""\n This message may contain {" ".join(propoganda_types)}"""
        reply += "\n\nToxicity score: " + str(toxicity_score)
        if toxicity_score >= 0.5:
            reply += """```\nThis message could be toxic!```"""
        return reply


client = ModBot()
client.run(discord_token)