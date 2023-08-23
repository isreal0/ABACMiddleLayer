#include <string.h>
#include <stdio.h>
#include <stdlib.h>

char* get_rule(char *rule, long i)
{
    sprintf(rule, "<Match MatchId=\"urn:oasis:names:tc:xacml:1.0:function:string-equal\"><AttributeValue DataType=\"http://www.w3.org/2001/XMLSchema#string\">user%ld</AttributeValue><AttributeDesignator AttributeId=\"urn:oasis:names:tc:xacml:1.0:subject:subject-id\" Category=\"urn:oasis:names:tc:xacml:1.0:subject-category:access-subject\" DataType=\"http://www.w3.org/2001/XMLSchema#string\" MustBePresent=\"true\"></AttributeDesignator></Match>", i);
    return rule;
}

int main(int argc, char **argv)
{
    long rule_amount = 10;
    if(argc == 2)
    {
        rule_amount = atoi(argv[1]);
    }
    printf("The program will create %ld rules in abacmlpolicy.xml\n", rule_amount);
    
    FILE *fp;
    fp = fopen("/home/ubuntu/project/abacml/resources/abacmlpolicy.xml", "w+");
    char start[1000], end[1000];
    sprintf(start, "<Policy xmlns=\"urn:oasis:names:tc:xacml:3.0:core:schema:wd-17\"  PolicyId=\"sample_policy_8\" RuleCombiningAlgId=\"urn:oasis:names:tc:xacml:1.0:rule-combining-algorithm:first-applicable\" Version=\"1.0\"><Description>Subject which name is in the target list can perform any anction on any resource.</Description><Target><AnyOf><AllOf>");
    fputs(start, fp);

    for(int i = 1; i <= rule_amount;i++){
        char rule[1000];
        get_rule(rule, i);
        fputs(rule, fp);
    }
    
    sprintf(end, "</AllOf></AnyOf></Target><Rule Effect=\"Permit\" RuleId=\"rule1\"/></Policy>");
    fputs(end, fp);
    fclose(fp);
    return 1;
}

