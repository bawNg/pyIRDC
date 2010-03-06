#!/usr/bin/env python

from ircbot import SingleServerIRCBot
from irclib import nm_to_n, nm_to_h, irc_lower, ip_numstr_to_quad, ip_quad_to_numstr
from DCHub import DCHubRemoteUser

class IRCBot(SingleServerIRCBot):
    def __init__(self, channel, nickname, server, port=6667, hub=None):
        SingleServerIRCBot.__init__(self, [(server, port)], nickname, nickname)
        self.connection.add_global_handler("all_events", self.on_all_events, -100)
        self.channel = channel
        self.channel_admins = []
        self.send_queue = []
        self.hub = hub
    
    ### IRC Methods ###
    def format_message(self, msg):
        # remove new lines
        msg = msg.replace("\r", "").replace("\n", "")
        # remove message terminator
        msg = msg.replace("|", "")
        # convert back html escaped chars
        msg = msg.replace("&#36;", "$").replace("&#124;", "|")
        return msg
    
    def send_message(self, *args, **tokens):
        target, msgs = self.channel, args[0]
        if len(args) == 2:
            target = args[0]
            msgs = args[1]
        if type(msgs) != list: msgs = [str(msgs)]
        for msg in msgs: self.connection.privmsg(target, self.format_message(msg))

    def send_notice(self, target, msg, **tokens):
        msgs = msg
        if type(msg) != list: msgs = [str(msg)]
        for msg in msgs: self.connection.notice(target, self.format_message(msg))
    
    def process_once(self):
        for user in self.hub.remote_users:
            continue
            if not user.outgoing: continue
            print "sending msg to [%s]: %r" % (user.nick, user.outgoing)
            while len(user.outgoing) > 0:
                msg = user.outgoing[:400] # split on max size
                self.send_message(user.nick, msg)
                user.outgoing = user.outgoing[len(msg):]
            
        self.ircobj.process_once(0.15)
    @property
    def nickname(): return self.connection.get_nickname()
    ### Events ###
    def on_all_events(self, c, e):
        if e.eventtype() != "all_raw_messages":
            print e.source(), e.eventtype().upper(), e.target(), e.arguments()

    def on_welcome(self, c, e):
        c.join(self.channel)
    
    def on_nicknameinuse(self, c, e):
        c.nick(c.get_nickname() + "_")

    def on_nick(self, c, e):
        pass
    
    def on_join(self, c, e):
        self.add_user_to_hub(nm_to_n(e.source()))
    
    def on_part(self, c, e):
        self.on_quit(c, e)
    
    def on_quit(self, c, e):
        self.remove_user_from_hub(nm_to_n(e.source()))
        for n in self.channel_admins:
            if n.lower() == nm_to_n(e.source()).lower():
                self.channel_admins.remove(n)
                break
    
    def on_privmsg(self, c, e):
        pass
    
    def on_pubmsg(self, c, e):
        nick = nm_to_n(e.source())
        msg = e.arguments()[0]
        self.hub.send_message("<%s> %s|" % (nick, msg))
    
    def on_action(self, c, e):
        nick = nm_to_n(e.source())
        bot = self.hub.get_remote_user(nick)
        if not bot:
            print "[on_action] got NULL user"
            return
        bot.sendmessage("* %s%s|" % (nick, e.arguments()[0]))
    
    def on_namreply(self, c, e):
        if e.arguments()[1] != self.channel: return
        for name in e.arguments()[2].split():
            if name.startswith('~') or name.startswith('&') or \
               name.startswith('@') or name.startswith('%'):
                self.channel_admins.append(name[1:])
                self.add_user_to_hub(name[1:], True)
                continue
            self.add_user_to_hub(name)

    def on_mode(self, c, e):
        if e.target() != self.channel: return
        nick = nm_to_n(e.source())
        if nick == c.get_nickname(): return
        args = e.arguments()[0]
        param = 0
        for mode in args:
            if mode == "+": add = True
            if mode == "-": add = False
            if mode.lower() in ['q', 'a', 'o', 'h']:
                if param - 1 >= len(e.arguments()):
                    print "[on_mode] Unable to parse mode. Breaking..."
                    break
                
                bot = self.hub.get_remote_user(e.arguments()[param])
                if add and not e.arguments()[param].lower() in [n.lower() for n in self.channel_admins]:
                    self.channel_admins.append(e.arguments()[param])
                    if bot:
                        self.hub.ops[bot.nick] = bot
                        self.hub.giveOpList()
                    continue
                
                # nick is channel admin
                if add: continue
                # remove nick from channel admins
                for n in self.channel_admins:
                    if n.lower() == e.arguments()[param].lower():
                        self.channel_admins.remove(n)
                        if bot:
                            del self.hub.ops[bot.nick]
                            self.hub.giveOpList()
                        break
            param += 1

    def on_whoreply(self, c, e):
        nick = e.arguments()[1]
    
    def on_endofwho(self, c, e):
        nick = e.arguments()[0]
    
    ### Wrapper methods ###
    def add_user_to_hub(self, nick, op=False):
        bot = DCHubRemoteUser(self.hub, nick, op)
        # Make bot appear as a user to the hub
        if bot.nick in self.hub.nicks: bot.nick = bot.nick + "_"
        self.hub.nicks[bot.nick] = bot
        self.hub.users[bot.nick] = bot
        print 'RemoteUserBot logged in: %s' % bot.idstring
        self.hub.giveHello(bot, newuser=True)
        self.hub.giveMyINFO(bot)
        if op:
            self.hub.ops[bot.nick] = bot
            self.hub.giveOpList()
        self.hub.remote_users.append(bot)
    
    def remove_user_from_hub(self, nick):
        bot = self.hub.get_remote_user(nick)
        if not bot:
            print "[remove_user_from_hub] got NULL user"
            return
        self.hub.removeuser(bot)
        self.hub.remote_users.remove(bot)
