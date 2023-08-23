#include <string.h>
#include <stdio.h>
#include <stdlib.h>

char* get_policy(char *policy, long i)
{
    
    sprintf(policy, "<Policy xmlns=\"urn:oasis:names:tc:xacml:3.0:core:schema:wd-17\"  PolicyId=\"sample_policy_8\" RuleCombiningAlgId=\"urn:oasis:names:tc:xacml:1.0:rule-combining-algorithm:first-applicable\" Version=\"1.0\"><Description>Subject with name user%ld can perform any anction on any resource.</Description><Target><AnyOf><AllOf><Match MatchId=\"urn:oasis:names:tc:xacml:1.0:function:string-equal\"><AttributeValue DataType=\"http://www.w3.org/2001/XMLSchema#string\">user%ld</AttributeValue><AttributeDesignator AttributeId=\"urn:oasis:names:tc:xacml:1.0:subject:subject-id\" Category=\"urn:oasis:names:tc:xacml:1.0:subject-category:access-subject\" DataType=\"http://www.w3.org/2001/XMLSchema#string\" MustBePresent=\"true\"></AttributeDesignator></Match></AllOf></AnyOf></Target><Rule Effect=\"Permit\" RuleId=\"rule1\"/></Policy>", i, i);
    
    return policy;
}

int main(int argc, char **argv)
{
    long file_amount = 10;
    long i = 1;
    char *dir = "/home/leomao/testc/resources/";
    if(argc == 3)
    {
        dir = argv[1];
        file_amount = atoi(argv[2]);
    }
    
    if(argc == 4)
    {
	dir = argv[1];
	i = atoi(argv[2]);
	file_amount = atoi(argv[3]);
    }

    printf("The program will create %ld files in %s.\n", file_amount, dir);
    
    for(;i<=file_amount;i++)
    {
        char filepath[200];
        sprintf(filepath, "%spolicy%ld.xml", dir, i);
        FILE *fp;
        fp = fopen(filepath, "w+");
        char policy[2000];
        fputs(get_policy(policy, i), fp);
        fclose(fp);
    }
    return 1;
}

